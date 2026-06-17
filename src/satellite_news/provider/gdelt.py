"""GDELT provider adapter around the existing GDELT fetcher."""

from __future__ import annotations

from satellite_news.fetcher.gdelt import (
    DEFAULT_GDELT_ENDPOINT,
    GDELTHTTPTransport,
    GDELTFetcher,
    limit_gdelt_queries,
)
from satellite_news.provider.base import company_override, dry_run_result
from satellite_news.provider.interface import ProviderResult
from satellite_news.schema import Company, NewsProviderConfig, PipelineContext, SourceConfig, SourceType


class GDELTProvider:
    provider_id = "gdelt_provider"

    def __init__(self, fetcher: GDELTFetcher | None = None) -> None:
        self.fetcher = fetcher or GDELTFetcher(
            transport=GDELTHTTPTransport(rate_limit_seconds=25.0, retries=1, backoff_seconds=90.0)
        )

    def fetch_raw_articles(
        self,
        *,
        company: Company,
        provider: NewsProviderConfig,
        context: PipelineContext,
    ) -> ProviderResult:
        source = gdelt_source_from_provider(company=company, provider=provider)
        queries = limit_gdelt_queries(
            self.fetcher.build_company_queries(company=company, source=source),
            context=context,
        )
        if context.dry_run:
            return dry_run_result(
                provider=provider,
                company=company,
                metadata={"query_count": len(queries), "queries": queries},
            )

        shadow_context = PipelineContext(
            run_id=context.run_id,
            started_at=context.started_at,
            config_dir=context.config_dir,
            output_dir=context.output_dir,
            dry_run=False,
            partial_run=context.partial_run,
            scheduled_slot=context.scheduled_slot,
            company_id=context.company_id,
            provider_id=context.provider_id,
            max_gdelt_queries=context.max_gdelt_queries,
            merge_policy=context.merge_policy,
            metadata={
                "partial_run": context.metadata.get("partial_run", context.partial_run),
                "scheduled_slot": context.metadata.get("scheduled_slot", context.scheduled_slot),
                "company_id": context.metadata.get("company_id", context.company_id),
                "company_ids": context.metadata.get("company_ids", ()),
                "provider_id": context.metadata.get("provider_id", context.provider_id),
                "provider_ids": context.metadata.get("provider_ids", ()),
                "max_gdelt_queries": context.metadata.get(
                    "max_gdelt_queries",
                    context.max_gdelt_queries,
                ),
                "merge_policy": context.metadata.get("merge_policy", context.merge_policy),
            },
        )
        articles = self.fetcher.fetch_raw_articles(
            company=company,
            source=source,
            context=shadow_context,
        )
        status_row = latest_status(shadow_context.metadata.get("fetch_statuses", ()))
        final_status = str(status_row.get("final_status") or status_row.get("status") or "failed")
        provider_status = provider_status_from_gdelt(final_status)
        return ProviderResult(
            provider_id=provider.id,
            company_id=company.id,
            articles=articles,
            status=provider_status,
            should_fallback=provider_status != "success",
            metadata={
                **status_row,
                "provider_status": provider_status,
                "gdelt_final_status": final_status,
                "cache_status": "not_implemented",
                "stale_fallback_available": False,
            },
        )


def gdelt_source_from_provider(*, company: Company, provider: NewsProviderConfig) -> SourceConfig:
    options = dict(provider.options)
    adapter_options = dict(options.get("adapter_options", {}) or {})
    if adapter_options.get("endpoint") in {None, "", "reserved"}:
        adapter_options["endpoint"] = DEFAULT_GDELT_ENDPOINT
    adapter_options.setdefault("mode", "ArtList")
    adapter_options.setdefault("format", "json")
    adapter_options.setdefault("maxrecords", 10)
    adapter_options.setdefault("sort", "HybridRel")
    adapter_options.setdefault("timeout_seconds", 20)
    adapter_options.setdefault("retries", 1)
    adapter_options.setdefault("backoff_seconds", 90.0)
    adapter_options.setdefault("rate_limit_seconds", 25.0)
    adapter_options["api_calls_allowed"] = True
    options["adapter_options"] = adapter_options

    override = company_override(company=company, provider=provider)
    if override and override.query_templates:
        options["company_query_overrides"] = {company.id: list(override.query_templates)}

    return SourceConfig(
        id=provider.id,
        type=SourceType.GDELT,
        rank_group=provider.rank_group,
        enabled=provider.enabled,
        description=provider.description,
        provider_id=provider.id,
        provider_priority=override.priority if override and override.priority is not None else provider.priority,
        fallback_to=provider.fallback.fallback_to,
        options=options,
    )


def latest_status(statuses: object) -> dict[str, object]:
    if isinstance(statuses, list) and statuses and isinstance(statuses[-1], dict):
        return dict(statuses[-1])
    if isinstance(statuses, tuple) and statuses and isinstance(statuses[-1], dict):
        return dict(statuses[-1])
    return {"status": "failed", "final_status": "failed", "error_message": "No GDELT status row."}


def provider_status_from_gdelt(final_status: str) -> str:
    if final_status in {"success", "partial_success"}:
        return "success"
    if final_status == "rate_limited":
        return "rate_limited"
    if final_status in {"no_results", "dry_run"}:
        return "no_results"
    return "failed"
