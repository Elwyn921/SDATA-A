"""Brave independent news-search provider."""

from __future__ import annotations

import os

from satellite_news.provider.base import (
    ProviderHTTPClient,
    build_raw_article,
    dry_run_result,
    failed_result,
    parse_datetime,
    provider_limit,
    provider_timeout,
    query_templates,
    skipped_no_secret_result,
    success_or_no_results_result,
    url_with_query,
)
from satellite_news.provider.interface import ProviderResult
from satellite_news.schema import Company, NewsProviderConfig, PipelineContext, SourceType


DEFAULT_ENDPOINT = "https://api.search.brave.com/res/v1/news/search"


class BraveNewsProvider:
    provider_id = "brave_news_provider"

    def __init__(self, client: ProviderHTTPClient | None = None) -> None:
        self.client = client or ProviderHTTPClient()

    def fetch_raw_articles(
        self,
        *,
        company: Company,
        provider: NewsProviderConfig,
        context: PipelineContext,
    ) -> ProviderResult:
        adapter_options = provider.options.get("adapter_options", {})
        secret_env = str(
            adapter_options.get("api_key_env") or "BRAVE_SEARCH_API_KEY"
            if isinstance(adapter_options, dict)
            else "BRAVE_SEARCH_API_KEY"
        )
        api_key = os.getenv(secret_env)
        if not api_key:
            return skipped_no_secret_result(provider=provider, company=company, secret_env=secret_env)
        queries = query_templates(
            company=company,
            provider=provider,
            default_template='"{company_name}" satellite',
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
        for query in queries:
            try:
                payload = self.client.get_json(
                    url_with_query(
                        endpoint,
                        {
                            "q": query,
                            "count": limit,
                            "freshness": "pm",
                            "search_lang": "en",
                        },
                    ),
                    timeout_seconds=provider_timeout(provider),
                    headers={
                        "Accept": "application/json",
                        "X-Subscription-Token": api_key,
                    },
                )
                for row in payload.get("results", ()) or ():
                    if not isinstance(row, dict):
                        continue
                    profile = row.get("profile") if isinstance(row.get("profile"), dict) else {}
                    article = build_raw_article(
                        company=company,
                        provider=provider,
                        source_type=SourceType.SEARCH_API,
                        title=str(row.get("title") or ""),
                        url=str(row.get("url") or ""),
                        published_at=parse_datetime(row.get("page_age")),
                        raw_text=str(row.get("description") or "") or None,
                        raw_payload=row,
                        metadata={
                            "brave_query": query,
                            "source_name": str(profile.get("long_name") or profile.get("url") or "Brave News"),
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
                "warning_count": len(warnings),
                "cache_status": "not_implemented",
                "stale_fallback_available": False,
            },
        )


def dedupe_articles(articles):
    rows = {}
    for article in articles:
        rows.setdefault(article.url, article)
    return list(rows.values())
