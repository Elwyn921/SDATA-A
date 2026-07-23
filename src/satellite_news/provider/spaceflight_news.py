"""Keyless Spaceflight News API provider."""

from __future__ import annotations

import time
import urllib.error

from satellite_news.provider.base import (
    ProviderHTTPClient,
    build_raw_article,
    dry_run_result,
    failed_result,
    parse_datetime,
    provider_limit,
    provider_timeout,
    query_templates,
    success_or_no_results_result,
    url_with_query,
)
from satellite_news.provider.interface import ProviderResult
from satellite_news.schema import Company, NewsProviderConfig, PipelineContext, SourceType


DEFAULT_ENDPOINT = "https://api.spaceflightnewsapi.net/v4/articles/"


class SpaceflightNewsAPIProvider:
    provider_id = "spaceflight_news_provider"

    def __init__(self, client: ProviderHTTPClient | None = None) -> None:
        self.client = client or ProviderHTTPClient()
        self._last_request_at: float | None = None

    def fetch_raw_articles(
        self,
        *,
        company: Company,
        provider: NewsProviderConfig,
        context: PipelineContext,
    ) -> ProviderResult:
        queries = query_templates(
            company=company,
            provider=provider,
            default_template='"{company_name}"',
        )
        if context.dry_run:
            return dry_run_result(
                provider=provider,
                company=company,
                metadata={"query_count": len(queries), "queries": queries},
            )

        endpoint = str(provider.options.get("endpoint") or DEFAULT_ENDPOINT)
        limit = provider_limit(provider)
        articles = []
        warnings = []
        successful_query_count = 0
        adapter_options = provider.options.get("adapter_options", {})
        if not isinstance(adapter_options, dict):
            adapter_options = {}
        rate_limit_seconds = float(adapter_options.get("rate_limit_seconds") or 0)
        retries = int(adapter_options.get("retries") or 0)
        backoff_seconds = float(adapter_options.get("backoff_seconds") or 0)
        for query in queries:
            try:
                payload = self.get_json_with_retry(
                    url=url_with_query(
                        endpoint,
                        {
                            "search": query.replace('"', ""),
                            "limit": limit,
                            "ordering": "-published_at",
                        },
                    ),
                    timeout_seconds=provider_timeout(provider),
                    rate_limit_seconds=rate_limit_seconds,
                    retries=retries,
                    backoff_seconds=backoff_seconds,
                )
                successful_query_count += 1
                for row in payload.get("results", ()) or ():
                    if not isinstance(row, dict):
                        continue
                    article = build_raw_article(
                        company=company,
                        provider=provider,
                        source_type=SourceType.SEARCH_API,
                        title=str(row.get("title") or ""),
                        url=str(row.get("url") or ""),
                        published_at=parse_datetime(row.get("published_at")),
                        raw_text=str(row.get("summary") or "") or None,
                        raw_payload=row,
                        metadata={
                            "spaceflight_news_query": query,
                            "source_name": str(row.get("news_site") or "Spaceflight News API"),
                        },
                    )
                    if article:
                        articles.append(article)
            except Exception as exc:  # pragma: no cover - network boundary
                warnings.append(f"{query}: {type(exc).__name__}: {exc}")

        if warnings and not articles:
            return failed_result(
                provider=provider,
                company=company,
                exc=RuntimeError("; ".join(warnings[:3])),
                metadata={"query_count": len(queries), "queries": queries},
            )
        return success_or_no_results_result(
            provider=provider,
            company=company,
            articles=tuple(dedupe_articles(articles)),
            warnings=tuple(warnings),
            metadata={
                "query_count": len(queries),
                "queries": queries,
                "successful_query_count": successful_query_count,
                "warning_count": len(warnings),
                "rate_limit_seconds": rate_limit_seconds,
                "cache_status": "not_implemented",
                "stale_fallback_available": False,
            },
        )

    def get_json_with_retry(
        self,
        *,
        url: str,
        timeout_seconds: int,
        rate_limit_seconds: float,
        retries: int,
        backoff_seconds: float,
    ):
        for attempt in range(retries + 1):
            self.wait_for_rate_limit(rate_limit_seconds)
            try:
                return self.client.get_json(url, timeout_seconds=timeout_seconds)
            except urllib.error.HTTPError as exc:
                if exc.code != 429 or attempt >= retries:
                    raise
                time.sleep(backoff_seconds * (attempt + 1))
        raise RuntimeError("Spaceflight News API retry loop exhausted.")

    def wait_for_rate_limit(self, seconds: float) -> None:
        if seconds <= 0:
            return
        now = time.monotonic()
        if self._last_request_at is not None:
            time.sleep(max(0.0, seconds - (now - self._last_request_at)))
        self._last_request_at = time.monotonic()


def dedupe_articles(articles):
    rows = {}
    for article in articles:
        rows.setdefault(article.url, article)
    return list(rows.values())
