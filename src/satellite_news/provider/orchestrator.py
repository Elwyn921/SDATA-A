"""Provider-based fetch orchestration."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from satellite_news.provider.base import (
    effective_provider_priority,
    provider_enabled_for_company,
    source_config_from_provider,
)
from satellite_news.provider.interface import NewsProviderRegistry, ProviderResult
from satellite_news.schema import Company, NewsItem, NewsProviderConfig, PipelineContext


@dataclass
class ProviderOrchestrator:
    registry: NewsProviderRegistry
    providers: tuple[NewsProviderConfig, ...] = ()
    run_all_enabled: bool = True
    fallback_statuses: set[str] = field(
        default_factory=lambda: {
            "no_results",
            "rate_limited",
            "skipped_no_secret",
            "failed",
        }
    )

    def fetch(
        self,
        *,
        companies: tuple[Company, ...],
        context: PipelineContext,
    ) -> tuple[NewsItem, ...]:
        items: list[NewsItem] = []
        seen_urls_by_company: dict[str, set[str]] = {}
        for company in companies:
            if not company.enabled:
                continue
            company_seen = seen_urls_by_company.setdefault(company.id, set())
            for provider_config in self.providers_for_company(company, context=context):
                result = self.fetch_provider(
                    company=company,
                    provider_config=provider_config,
                    context=context,
                )
                record_provider_status(
                    context=context,
                    company=company,
                    provider=provider_config,
                    result=result,
                )
                source = source_config_from_provider(provider_config, company=company)
                for article in result.articles:
                    url_key = article.url.strip().lower()
                    if not url_key or url_key in company_seen:
                        continue
                    company_seen.add(url_key)
                    items.append(article.to_news_item(source, collected_at=context.started_at))
                if not self.run_all_enabled and result.status not in self.fallback_statuses:
                    break
        return tuple(items)

    def providers_for_company(
        self,
        company: Company,
        context: PipelineContext | None = None,
    ) -> tuple[NewsProviderConfig, ...]:
        requested_provider_ids = provider_filter_from_context(context)
        enabled = [
            provider
            for provider in self.providers
            if provider_enabled_for_company(company=company, provider=provider)
            and (not requested_provider_ids or provider.id in requested_provider_ids)
        ]
        return tuple(
            sorted(
                enabled,
                key=lambda provider: effective_provider_priority(company=company, provider=provider),
            )
        )

    def fetch_provider(
        self,
        *,
        company: Company,
        provider_config: NewsProviderConfig,
        context: PipelineContext,
    ) -> ProviderResult:
        provider = self.registry.get(provider_config.id)
        try:
            return provider.fetch_raw_articles(
                company=company,
                provider=provider_config,
                context=context,
            )
        except Exception as exc:  # pragma: no cover - defensive pipeline boundary
            return ProviderResult(
                provider_id=provider_config.id,
                company_id=company.id,
                status="failed",
                should_fallback=True,
                metadata={
                    "error_type": type(exc).__name__,
                    "error_message": str(exc),
                    "cache_status": "not_implemented",
                    "stale_fallback_available": False,
                },
            )


def provider_filter_from_context(context: PipelineContext | None) -> set[str]:
    if context is None:
        return set()
    provider_ids = context.metadata.get("provider_ids", ())
    if isinstance(provider_ids, (list, tuple, set)):
        return {str(value) for value in provider_ids if str(value)}
    if context.provider_id:
        return {value for value in context.provider_id.split(",") if value}
    return set()


def record_provider_status(
    *,
    context: PipelineContext,
    company: Company,
    provider: NewsProviderConfig,
    result: ProviderResult,
) -> None:
    now = datetime.now(timezone.utc)
    metadata = dict(result.metadata)
    status = result.status
    status_row: dict[str, Any] = {
        "company_id": company.id,
        "company_name": company.canonical_name,
        "scheduled_company_id": context.company_id or context.metadata.get("company_id"),
        "scheduled_provider_id": context.provider_id or context.metadata.get("provider_id"),
        "scheduled_slot": context.scheduled_slot or context.metadata.get("scheduled_slot"),
        "partial_run": bool(context.partial_run or context.metadata.get("partial_run", False)),
        "merge_policy": context.merge_policy or context.metadata.get("merge_policy"),
        "max_gdelt_queries": context.max_gdelt_queries
        if context.max_gdelt_queries is not None
        else context.metadata.get("max_gdelt_queries"),
        "provider_id": provider.id,
        "provider_type": provider.type.value,
        "source_id": provider.id,
        "source_type": provider.type.value,
        "rank_group": provider.rank_group,
        "provider_priority": effective_provider_priority(company=company, provider=provider),
        "status": status,
        "provider_status": status,
        "final_status": status,
        "should_fallback": result.should_fallback,
        "item_count": len(result.articles),
        "article_count": len(result.articles),
        "rate_limited": status == "rate_limited" or bool(metadata.get("rate_limited", False)),
        "retry_count": int(metadata.get("retry_count") or 0),
        "query_count": int(metadata.get("query_count") or 0),
        "successful_query_count": int(metadata.get("successful_query_count") or 0),
        "error_type": metadata.get("error_type"),
        "error_message": metadata.get("error_message") or metadata.get("reason"),
        "reason": metadata.get("reason") or metadata.get("error_message"),
        "warnings": list(result.warnings),
        "started_at": None,
        "finished_at": now,
        "metadata": {
            "cache_status": metadata.get("cache_status", "not_implemented"),
            "stale_fallback_available": bool(metadata.get("stale_fallback_available", False)),
            "scheduled_slot": context.scheduled_slot or context.metadata.get("scheduled_slot"),
            "company_id": context.company_id or context.metadata.get("company_id"),
            "provider_id": context.provider_id or context.metadata.get("provider_id"),
            "partial_run": bool(context.partial_run or context.metadata.get("partial_run", False)),
            "merge_policy": context.merge_policy or context.metadata.get("merge_policy"),
            "max_gdelt_queries": context.max_gdelt_queries
            if context.max_gdelt_queries is not None
            else context.metadata.get("max_gdelt_queries"),
            **metadata,
        },
    }
    for key in (
        "queries",
        "feed_count",
        "feeds",
        "entrypoint_count",
        "entrypoints",
        "secret_env",
        "gdelt_final_status",
    ):
        if key in metadata:
            status_row[key] = metadata[key]
    context.metadata.setdefault("fetch_statuses", []).append(status_row)
