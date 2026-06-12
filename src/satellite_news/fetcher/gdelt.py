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
from typing import Any, Protocol

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
    ) -> None:
        self.timeout_seconds = timeout_seconds
        self.retries = max(0, retries)
        self.backoff_seconds = max(0.0, backoff_seconds)
        self.rate_limit_seconds = max(0.0, rate_limit_seconds)
        self.sleep = sleep
        self.clock = clock
        self._last_request_at: float | None = None

    def search(self, request: GDELTRequest) -> dict[str, Any]:
        url = f"{request.endpoint}?{urllib.parse.urlencode(request.params())}"
        http_request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        last_error: Exception | None = None

        for attempt in range(self.retries + 1):
            self._wait_for_rate_limit()
            try:
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
                return decoded
            except (urllib.error.URLError, TimeoutError, OSError, GDELTTransportError) as exc:
                last_error = exc
                if attempt >= self.retries:
                    break
                self.sleep(self._retry_delay(exc, attempt))

        raise GDELTTransportError(f"GDELT request failed: {last_error}") from last_error

    def _wait_for_rate_limit(self) -> None:
        if self.rate_limit_seconds <= 0:
            self._last_request_at = self.clock()
            return
        now = self.clock()
        if self._last_request_at is not None:
            elapsed = now - self._last_request_at
            if elapsed < self.rate_limit_seconds:
                self.sleep(self.rate_limit_seconds - elapsed)
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


class GDELTFetcher:
    def __init__(self, transport: GDELTTransport | None = None) -> None:
        self.transport = transport or GDELTHTTPTransport()

    def build_request(self, *, company: Company, source: SourceConfig) -> GDELTRequest:
        options = source.options
        adapter_options = options.get("adapter_options", {})
        return GDELTRequest(
            company_id=company.id,
            source_id=source.id,
            endpoint=str(adapter_options.get("endpoint") or DEFAULT_GDELT_ENDPOINT),
            query=build_company_query(company=company, source=source),
            mode=str(adapter_options.get("mode") or "ArtList"),
            format=str(adapter_options.get("format") or "json"),
            max_records=int(
                options.get("max_items_per_company") or adapter_options.get("maxrecords") or 20
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

        request = self.build_request(company=company, source=source)
        if context.dry_run or not gdelt_api_calls_allowed(source) or self.transport is None:
            return ()

        try:
            payload = self.transport.search(request)
        except GDELTTransportError as exc:
            LOGGER.warning("GDELT fetch failed company_id=%s: %s", company.id, exc)
            return ()
        articles = payload.get("articles", ())
        if not isinstance(articles, list):
            return ()
        return tuple(
            article
            for row in articles
            if isinstance(row, dict)
            for article in [
                raw_article_from_gdelt_row(row, company=company, source=source, request=request)
            ]
            if article is not None
        )

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


def build_company_query(*, company: Company, source: SourceConfig) -> str:
    overrides = source.options.get("company_query_overrides", {})
    if company.id in overrides:
        return str(overrides[company.id])

    template = str(
        source.options.get("query_template")
        or (
            '("{company_name}" OR {company_alias_terms}) '
            "AND (satellite OR launch OR constellation OR broadband OR space)"
        )
    )
    aliases = tuple(alias for alias in company.aliases if alias)
    alias_terms = " OR ".join(quote_query_term(alias) for alias in aliases[:8])
    if not alias_terms:
        alias_terms = quote_query_term(company.canonical_name)
    return template.format(
        company_name=company.canonical_name,
        company_alias_terms=alias_terms,
    )


def quote_query_term(value: str) -> str:
    cleaned = " ".join(value.split())
    if not cleaned:
        return '""'
    if any(char.isspace() for char in cleaned) or any(ord(char) > 127 for char in cleaned):
        return f'"{cleaned}"'
    return cleaned


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
