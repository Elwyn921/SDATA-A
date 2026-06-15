"""NewsAPI provider adapter."""

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


DEFAULT_NEWSAPI_ENDPOINT = "https://newsapi.org/v2/everything"


class NewsAPIProvider:
    provider_id = "newsapi_provider"

    def __init__(self, client: ProviderHTTPClient | None = None) -> None:
        self.client = client or ProviderHTTPClient()

    def fetch_raw_articles(
        self,
        *,
        company: Company,
        provider: NewsProviderConfig,
        context: PipelineContext,
    ) -> ProviderResult:
        secret_env = api_key_env(provider, "NEWSAPI_KEY")
        api_key = os.getenv(secret_env)
        if not api_key:
            return skipped_no_secret_result(provider=provider, company=company, secret_env=secret_env)
        queries = query_templates(
            company=company,
            provider=provider,
            default_template='"{company_name}" AND (satellite OR launch OR constellation)',
        )
        if context.dry_run:
            return dry_run_result(
                provider=provider,
                company=company,
                metadata={"query_count": len(queries), "queries": queries},
            )

        endpoint = str(provider.options.get("endpoint") or DEFAULT_NEWSAPI_ENDPOINT)
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
                            "apiKey": api_key,
                            "pageSize": limit,
                            "sortBy": "publishedAt",
                        },
                    ),
                    timeout_seconds=provider_timeout(provider),
                )
                api_status = str(payload.get("status") or "")
                if api_status and api_status != "ok":
                    raise RuntimeError(str(payload.get("message") or f"NewsAPI status={api_status}"))
                for row in payload.get("articles", ()) or ():
                    if not isinstance(row, dict):
                        continue
                    article = build_raw_article(
                        company=company,
                        provider=provider,
                        source_type=SourceType.NEWSAPI,
                        title=str(row.get("title") or ""),
                        url=str(row.get("url") or ""),
                        published_at=parse_datetime(row.get("publishedAt")),
                        raw_text=str(row.get("description") or row.get("content") or "") or None,
                        raw_payload=row,
                        metadata={
                            "newsapi_query": query,
                            "source_name": source_name(row.get("source")),
                        },
                    )
                    if article:
                        articles.append(article)
                    if len(articles) >= limit:
                        break
            except Exception as exc:  # pragma: no cover - exercised via provider tests
                warnings.append(f"{query}: {type(exc).__name__}: {exc}")
            if len(articles) >= limit:
                break

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
            articles=dedupe_articles(articles),
            warnings=tuple(warnings),
            metadata={
                "query_count": len(queries),
                "queries": queries,
                "warning_count": len(warnings),
                "cache_status": "not_implemented",
                "stale_fallback_available": False,
            },
        )


def api_key_env(provider: NewsProviderConfig, default: str) -> str:
    adapter_options = provider.options.get("adapter_options", {})
    if isinstance(adapter_options, dict):
        return str(adapter_options.get("api_key_env") or default)
    return default


def source_name(value: object) -> str:
    if isinstance(value, dict):
        return str(value.get("name") or "")
    return str(value or "")


def dedupe_articles(articles):
    seen = set()
    unique = []
    for article in articles:
        if article.url in seen:
            continue
        seen.add(article.url)
        unique.append(article)
    return unique
