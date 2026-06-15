"""Minimal GDELT fetcher with dry-run first behavior."""

from __future__ import annotations

import hashlib
import json
import logging
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Protocol

from satellite_news.schema import (
    Company,
    NewsItem,
    PipelineContext,
    RawArticle,
    SourceConfig,
    SourceType,
)


DEFAULT_GDELT_ENDPOINT = "https://api.gdeltproject.org/api/v2/doc/doc"
USER_AGENT = "SDATA-A Satellite News Pipeline/0.1"
LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class GDELTRequest:
    company_id: str
    source_id: str
    endpoint: str
    query: str
    mode: str = "ArtList"
    format: str = "json"
    max_records: int = 20
    sort: str | None = None
    timespan: str | None = None

    def params(self) -> dict[str, str | int]:
        params: dict[str, str | int] = {
            "query": self.query,
            "mode": self.mode,
            "format": self.format,
            "maxrecords": self.max_records,
        }
        if self.sort:
            params["sort"] = self.sort
        if self.timespan:
            params["timespan"] = self.timespan
        return params


class GDELTTransport(Protocol):
    def search(self, request: GDELTRequest) -> dict[str, Any]:
        """Return a decoded GDELT-like payload for tests or future HTTP adapters."""


class GDELTTransportError(RuntimeError):
    """Raised when the GDELT transport cannot return a decoded payload."""

    def __init__(self, message: str, *, rate_limited: bool = False, retry_count: int = 0) -> None:
        super().__init__(message)
        self.rate_limited = rate_limited
        self.retry_count = retry_count


class GDELTHTTPTransport:
    def __init__(
        self,
        *,
        timeout_seconds: int = 20,
        retries: int = 2,
        backoff_seconds: float = 1.0,
        rate_limit_seconds: float = 3.0,
        sleep: Any = time.sleep,
        clock: Any = time.monotonic,
        progress: Callable[[str], None] | None = None,
    ) -> None:
        self.timeout_seconds = timeout_seconds
        self.retries = max(0, retries)
        self.backoff_seconds = max(0.0, backoff_seconds)
        self.rate_limit_seconds = max(0.0, rate_limit_seconds)
        self.sleep = sleep
        self.clock = clock
        self.progress = progress
        self._last_request_at: float | None = None

    def search(self, request: GDELTRequest) -> dict[str, Any]:
        url = f"{request.endpoint}?{urllib.parse.urlencode(request.params())}"
        http_request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        last_error: Exception | None = None
        rate_limited = False
        retry_count = 0

        for attempt in range(self.retries + 1):
            self._wait_for_rate_limit(request)
            try:
                self._emit(
                    f"[GDELT] requesting company={request.company_id} "
                    f"attempt={attempt + 1}/{self.retries + 1}"
                )
                with urllib.request.urlopen(http_request, timeout=self.timeout_seconds) as response:
                    payload = response.read().decode("utf-8")
                try:
                    decoded = json.loads(payload)
                except json.JSONDecodeError as exc:
                    preview = " ".join(payload[:120].split())
                    raise GDELTTransportError(
                        f"GDELT response was not JSON: {preview or '<empty response>'}"
                    ) from exc
                if not isinstance(decoded, dict):
                    raise GDELTTransportError("GDELT response was not a JSON object.")
                decoded["_transport_meta"] = {
                    "rate_limited": rate_limited,
                    "retry_count": retry_count,
                }
                return decoded
            except (urllib.error.URLError, TimeoutError, OSError, GDELTTransportError) as exc:
                last_error = exc
                rate_limited = rate_limited or is_rate_limited_error(exc)
                if attempt >= self.retries:
                    break
                delay = self._retry_delay(exc, attempt)
                retry_count += 1
                self._emit(
                    f"[GDELT] retrying company={request.company_id} "
                    f"in {delay:.1f}s after {type(exc).__name__}: {exc}"
                )
                self.sleep(delay)

        raise GDELTTransportError(
            f"GDELT request failed: {last_error}",
            rate_limited=rate_limited,
            retry_count=retry_count,
        ) from last_error

    def _wait_for_rate_limit(self, request: GDELTRequest) -> None:
        if self.rate_limit_seconds <= 0:
            self._last_request_at = self.clock()
            return
        now = self.clock()
        if self._last_request_at is not None:
            elapsed = now - self._last_request_at
            if elapsed < self.rate_limit_seconds:
                delay = self.rate_limit_seconds - elapsed
                self._emit(f"[GDELT] waiting {delay:.1f}s before company={request.company_id}")
                self.sleep(delay)
                now = self.clock()
        self._last_request_at = now

    def _retry_delay(self, exc: Exception, attempt: int) -> float:
        retry_after = None
        if isinstance(exc, urllib.error.HTTPError):
            retry_after = exc.headers.get("Retry-After")
            if exc.code == 429 and not retry_after:
                return max(30.0, self.backoff_seconds * (2**attempt))
        if retry_after:
            try:
                return max(float(retry_after), self.backoff_seconds)
            except ValueError:
                return self.backoff_seconds * (2**attempt)
        return self.backoff_seconds * (2**attempt)

    def _emit(self, message: str) -> None:
        if self.progress:
            self.progress(message)


class GDELTFetcher:
    def __init__(self, transport: GDELTTransport | None = None) -> None:
        self.transport = transport or GDELTHTTPTransport()

    def build_company_queries(self, *, company: Company, source: SourceConfig) -> list[str]:
        return build_company_queries(company=company, source=source)

    def _emit(self, message: str) -> None:
        progress = getattr(self.transport, "progress", None)
        if callable(progress):
            progress(message)

    def build_request(
        self,
        *,
        company: Company,
        source: SourceConfig,
        query: str | None = None,
    ) -> GDELTRequest:
        options = source.options
        adapter_options = options.get("adapter_options", {})
        return GDELTRequest(
            company_id=company.id,
            source_id=source.id,
            endpoint=str(adapter_options.get("endpoint") or DEFAULT_GDELT_ENDPOINT),
            query=query or build_company_query(company=company, source=source),
            mode=str(adapter_options.get("mode") or "ArtList"),
            format=str(adapter_options.get("format") or "json"),
            max_records=int(
                adapter_options.get("maxrecords")
                if adapter_options.get("maxrecords") is not None
                else options.get("max_items_per_company") or 20
            ),
            sort=adapter_options.get("sort"),
            timespan=adapter_options.get("timespan"),
        )

    def fetch_raw_articles(
        self,
        *,
        company: Company,
        source: SourceConfig,
        context: PipelineContext,
    ) -> tuple[RawArticle, ...]:
        if source.type is not SourceType.GDELT:
            return ()

        queries = build_company_queries(company=company, source=source)
        if context.dry_run or not gdelt_api_calls_allowed(source) or self.transport is None:
            record_fetch_status(
                context,
                company=company,
                source=source,
                final_status="dry_run",
                item_count=0,
                query_summary=queries,
            )
            return ()

        raw_articles: list[RawArticle] = []
        seen_urls: set[str] = set()
        failed_queries: list[str] = []
        successful_queries = 0
        rate_limited = False
        retry_count = 0

        for index, query in enumerate(queries, start=1):
            request = self.build_request(company=company, source=source, query=query)
            self._emit(
                f"[GDELT] company={company.id} query={index}/{len(queries)} "
                f"maxrecords={request.max_records}"
            )
            try:
                payload = self.transport.search(request)
            except GDELTTransportError as exc:
                LOGGER.warning(
                    "GDELT fetch failed company_id=%s query=%s: %s",
                    company.id,
                    query,
                    exc,
                )
                rate_limited = rate_limited or exc.rate_limited
                retry_count += exc.retry_count
                failed_queries.append(f"{query}: {exc}")
                if exc.rate_limited:
                    self._emit(
                        f"[GDELT] company={company.id} hit rate limit; "
                        "skipping remaining queries for this company"
                    )
                    break
                continue
            transport_meta = payload.get("_transport_meta", {})
            if isinstance(transport_meta, dict):
                rate_limited = rate_limited or bool(transport_meta.get("rate_limited", False))
                retry_count += int(transport_meta.get("retry_count") or 0)
            articles = payload.get("articles", ())
            if not isinstance(articles, list):
                failed_queries.append(f"{query}: response did not contain an articles list")
                continue
            successful_queries += 1
            for row in articles:
                if not isinstance(row, dict):
                    continue
                article = raw_article_from_gdelt_row(
                    row,
                    company=company,
                    source=source,
                    request=request,
                )
                if article is None or article.url in seen_urls:
                    continue
                seen_urls.add(article.url)
                raw_articles.append(article)

        if raw_articles and not failed_queries:
            final_status = "success"
            reason = ""
        elif raw_articles:
            final_status = "partial_success"
            reason = f"{len(failed_queries)} query(s) failed but {successful_queries} succeeded."
        elif rate_limited:
            final_status = "rate_limited"
            reason = "; ".join(failed_queries[:3]) or "GDELT rate limited the request."
        elif failed_queries:
            final_status = "failed"
            reason = "; ".join(failed_queries[:3])
        else:
            final_status = "no_results"
            reason = "GDELT returned zero usable articles."

        record_fetch_status(
            context,
            company=company,
            source=source,
            final_status=final_status,
            item_count=len(raw_articles),
            query_summary=queries,
            reason=reason,
            successful_queries=successful_queries,
            failed_queries=len(failed_queries),
            rate_limited=rate_limited,
            retry_count=retry_count,
        )
        return tuple(raw_articles)

    def fetch(
        self,
        *,
        company: Company,
        source: SourceConfig,
        context: PipelineContext,
    ) -> tuple[NewsItem, ...]:
        raw_articles = self.fetch_raw_articles(company=company, source=source, context=context)
        return tuple(
            article.to_news_item(source, collected_at=context.started_at)
            for article in raw_articles
        )


def gdelt_api_calls_allowed(source: SourceConfig) -> bool:
    adapter_options = source.options.get("adapter_options", {})
    return bool(adapter_options.get("api_calls_allowed", False))


def is_rate_limited_error(exc: Exception) -> bool:
    if isinstance(exc, urllib.error.HTTPError):
        return exc.code == 429
    if isinstance(exc, GDELTTransportError):
        return exc.rate_limited
    return "429" in str(exc) or "Too Many Requests" in str(exc)


def record_fetch_status(
    context: PipelineContext,
    *,
    company: Company,
    source: SourceConfig,
    final_status: str,
    item_count: int,
    query_summary: list[str],
    reason: str = "",
    successful_queries: int = 0,
    failed_queries: int = 0,
    rate_limited: bool = False,
    retry_count: int = 0,
) -> None:
    statuses = context.metadata.setdefault("fetch_statuses", [])
    statuses.append(
        {
            "company_id": company.id,
            "company_name": company.canonical_name,
            "source_id": source.id,
            "source_type": source.type.value,
            "status": final_status,
            "final_status": final_status,
            "rate_limited": rate_limited,
            "retry_count": retry_count,
            "item_count": item_count,
            "reason": reason,
            "error_message": reason or None,
            "query_count": len(query_summary),
            "successful_query_count": successful_queries,
            "successful_queries": successful_queries,
            "failed_queries": failed_queries,
            "queries": query_summary,
        }
    )


def build_company_query(*, company: Company, source: SourceConfig) -> str:
    return build_company_queries(company=company, source=source)[0]


def build_company_queries(*, company: Company, source: SourceConfig) -> list[str]:
    overrides = source.options.get("company_query_overrides", {})
    override = overrides.get(company.id)
    if isinstance(override, str):
        return [override]
    if isinstance(override, list):
        return [str(query) for query in override if str(query).strip()]

    template = str(
        source.options.get("query_template")
        or (
            '("{company_name}" OR {company_alias_terms}) '
            "AND (satellite OR launch OR constellation OR broadband OR space)"
        )
    )
    aliases = [company.canonical_name, *[alias for alias in company.aliases if alias]]
    if not aliases:
        aliases = [company.canonical_name]
    query_terms = [quote_query_term(term) for term in aliases if term]
    if len(query_terms) == 1:
        return [
            template.format(
                company_name=company.canonical_name,
                company_alias_terms=query_terms[0],
            )
        ]

    queries: list[str] = []
    chunk_size = 2
    for start in range(0, len(query_terms), chunk_size):
        chunk = query_terms[start : start + chunk_size]
        queries.append(
            template.format(
                company_name=company.canonical_name,
                company_alias_terms=" OR ".join(chunk),
            )
        )
    return dedupe_queries(queries)


def quote_query_term(value: str) -> str:
    cleaned = " ".join(value.split())
    if not cleaned:
        return '""'
    if any(char.isspace() for char in cleaned) or any(ord(char) > 127 for char in cleaned):
        return f'"{cleaned}"'
    return cleaned


def dedupe_queries(queries: list[str]) -> list[str]:
    seen = set()
    unique = []
    for query in queries:
        normalized = " ".join(query.split())
        if normalized and normalized not in seen:
            seen.add(normalized)
            unique.append(query)
    return unique


def raw_article_from_gdelt_row(
    row: dict[str, Any],
    *,
    company: Company,
    source: SourceConfig,
    request: GDELTRequest,
) -> RawArticle | None:
    title = str(row.get("title") or "").strip()
    url = str(row.get("url") or "").strip()
    if not title or not url:
        return None

    raw_text = str(row.get("snippet") or row.get("summary") or "").strip() or None
    published_at = parse_gdelt_datetime(row.get("seendate") or row.get("publishedAt"))
    article_id = stable_article_id(company_id=company.id, source_id=source.id, url=url, title=title)
    return RawArticle(
        id=article_id,
        company_id=company.id,
        company_name=company.canonical_name,
        source_id=source.id,
        source_type=SourceType.GDELT,
        title=title,
        url=url,
        published_at=published_at,
        language=str(row.get("language") or "") or None,
        raw_text=raw_text,
        raw_payload=row,
        metadata={
            "gdelt_query": request.query,
            "gdelt_domain": row.get("domain") or "",
            "gdelt_source_country": row.get("sourceCountry") or "",
            "image_url": row.get("socialimage") or "",
        },
    )


def parse_gdelt_datetime(value: Any) -> datetime | None:
    if not value:
        return None
    text = str(value).strip()
    for fmt in ("%Y%m%d%H%M%S", "%Y%m%dT%H%M%SZ", "%Y-%m-%dT%H:%M:%SZ"):
        try:
            return datetime.strptime(text, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def stable_article_id(*, company_id: str, source_id: str, url: str, title: str) -> str:
    basis = f"{company_id}:{source_id}:{url or title}"
    return hashlib.sha256(basis.encode("utf-8")).hexdigest()[:16]
