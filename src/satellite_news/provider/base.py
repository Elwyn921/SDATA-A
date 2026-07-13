"""Shared helpers for news provider adapters."""

from __future__ import annotations

import hashlib
import json
import re
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any

from satellite_news.provider.interface import ProviderResult
from satellite_news.schema import (
    Company,
    CompanyProviderConfig,
    NewsProviderConfig,
    RawArticle,
    SourceConfig,
    SourceType,
)


PROVIDER_SUCCESS_STATUSES = {"success"}
PROVIDER_FALLBACK_STATUSES = {
    "no_results",
    "rate_limited",
    "skipped_no_secret",
    "failed",
}
USER_AGENT = "SDATA-A Satellite News Pipeline/0.1"


class ProviderHTTPClient:
    """Small urllib wrapper kept injectable for mock tests."""

    def get_text(
        self,
        url: str,
        *,
        timeout_seconds: int = 20,
        headers: dict[str, str] | None = None,
    ) -> str:
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, **(headers or {})})
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            charset = response.headers.get_content_charset() or "utf-8"
            return response.read().decode(charset, errors="replace")

    def get_json(
        self,
        url: str,
        *,
        timeout_seconds: int = 20,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        text = self.get_text(url, timeout_seconds=timeout_seconds, headers=headers)
        decoded = json.loads(text)
        if not isinstance(decoded, dict):
            raise ValueError("Provider response was not a JSON object.")
        return decoded


def company_override(
    *,
    company: Company,
    provider: NewsProviderConfig,
) -> CompanyProviderConfig | None:
    return provider.company_overrides.get(company.id)


def provider_enabled_for_company(
    *,
    company: Company,
    provider: NewsProviderConfig,
) -> bool:
    if not provider.enabled:
        return False
    override = company_override(company=company, provider=provider)
    return True if override is None else override.enabled


def effective_provider_priority(
    *,
    company: Company,
    provider: NewsProviderConfig,
) -> int:
    override = company_override(company=company, provider=provider)
    if override and override.priority is not None:
        return override.priority
    return provider.priority


def source_config_from_provider(
    provider: NewsProviderConfig,
    *,
    company: Company | None = None,
) -> SourceConfig:
    priority = (
        effective_provider_priority(company=company, provider=provider)
        if company is not None
        else provider.priority
    )
    return SourceConfig(
        id=provider.id,
        type=provider.type,
        rank_group=provider.rank_group,
        enabled=provider.enabled,
        description=provider.description,
        provider_id=provider.id,
        provider_priority=priority,
        fallback_to=provider.fallback.fallback_to,
        options=dict(provider.options),
    )


def provider_timeout(provider: NewsProviderConfig, default: int = 20) -> int:
    adapter_options = provider.options.get("adapter_options", {})
    if not isinstance(adapter_options, dict):
        return default
    return int(adapter_options.get("timeout_seconds") or default)


def provider_limit(provider: NewsProviderConfig, default: int = 10) -> int:
    adapter_options = provider.options.get("adapter_options", {})
    if isinstance(adapter_options, dict) and adapter_options.get("max_items") is not None:
        return int(adapter_options["max_items"])
    if provider.options.get("max_items_per_company") is not None:
        return int(provider.options["max_items_per_company"])
    return default


def query_templates(
    *,
    company: Company,
    provider: NewsProviderConfig,
    default_template: str,
) -> list[str]:
    override = company_override(company=company, provider=provider)
    if override and override.query_templates:
        return dedupe([template for template in override.query_templates if template.strip()])

    configured = provider.options.get("query_template")
    template = str(configured or default_template)
    aliases = [company.canonical_name, *company.aliases]
    alias_terms = " OR ".join(quote_term(alias) for alias in aliases if alias)
    return [template.format(company_name=company.canonical_name, company_alias_terms=alias_terms)]


def company_terms(
    *,
    company: Company,
    provider: NewsProviderConfig,
) -> tuple[str, ...]:
    terms = [company.canonical_name, *company.aliases]
    override = company_override(company=company, provider=provider)
    if override:
        terms.extend(extract_match_terms(" ".join(override.query_templates)))
        terms.extend(str(value) for value in override.options.get("keywords", ()) or ())
    terms.extend(extract_match_terms(str(provider.options.get("query_template") or "")))
    return tuple(dedupe(term for term in terms if len(term.strip()) >= 2))


def text_matches_company(
    *,
    text: str,
    company: Company,
    provider: NewsProviderConfig,
) -> bool:
    haystack = normalize_text(text)
    if not haystack:
        return False
    return any(normalize_text(term) in haystack for term in company_terms(company=company, provider=provider))


def build_raw_article(
    *,
    company: Company,
    provider: NewsProviderConfig,
    source_type: SourceType,
    title: str,
    url: str,
    published_at: datetime | None = None,
    language: str | None = None,
    raw_text: str | None = None,
    raw_payload: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
) -> RawArticle | None:
    title = " ".join(title.split())
    url = url.strip()
    if not title or not url:
        return None
    return RawArticle(
        id=stable_article_id(company_id=company.id, source_id=provider.id, url=url, title=title),
        company_id=company.id,
        company_name=company.canonical_name,
        source_id=provider.id,
        source_type=source_type,
        title=title,
        url=url,
        provider_id=provider.id,
        provider_priority=effective_provider_priority(company=company, provider=provider),
        published_at=published_at,
        language=language,
        raw_text=raw_text,
        raw_payload=raw_payload or {},
        metadata=metadata or {},
    )


def success_or_no_results_result(
    *,
    provider: NewsProviderConfig,
    company: Company,
    articles: list[RawArticle],
    metadata: dict[str, Any] | None = None,
    warnings: tuple[str, ...] = (),
) -> ProviderResult:
    status = "success" if articles else "no_results"
    return ProviderResult(
        provider_id=provider.id,
        company_id=company.id,
        articles=tuple(articles),
        status=status,
        should_fallback=status != "success",
        warnings=warnings,
        metadata=metadata or {},
    )


def skipped_no_secret_result(
    *,
    provider: NewsProviderConfig,
    company: Company,
    secret_env: str,
) -> ProviderResult:
    return ProviderResult(
        provider_id=provider.id,
        company_id=company.id,
        status="skipped_no_secret",
        should_fallback=True,
        metadata={
            "error_message": f"Missing required environment variable: {secret_env}",
            "secret_env": secret_env,
            "cache_status": "not_implemented",
            "stale_fallback_available": False,
        },
    )


def failed_result(
    *,
    provider: NewsProviderConfig,
    company: Company,
    exc: Exception,
    status: str = "failed",
    metadata: dict[str, Any] | None = None,
) -> ProviderResult:
    return ProviderResult(
        provider_id=provider.id,
        company_id=company.id,
        status=status,
        should_fallback=True,
        metadata={
            "error_type": type(exc).__name__,
            "error_message": str(exc),
            "cache_status": "not_implemented",
            "stale_fallback_available": False,
            **(metadata or {}),
        },
    )


def dry_run_result(
    *,
    provider: NewsProviderConfig,
    company: Company,
    metadata: dict[str, Any] | None = None,
) -> ProviderResult:
    return ProviderResult(
        provider_id=provider.id,
        company_id=company.id,
        status="no_results",
        should_fallback=True,
        metadata={
            "dry_run": True,
            "reason": "Dry run: provider did not make network requests.",
            "cache_status": "not_implemented",
            "stale_fallback_available": False,
            **(metadata or {}),
        },
    )


def parse_datetime(value: Any) -> datetime | None:
    if not value:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        parsed = parsedate_to_datetime(text)
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except (TypeError, ValueError, IndexError, OverflowError):
        pass
    normalized = text.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except ValueError:
        return None


def quote_term(value: str) -> str:
    cleaned = " ".join(value.split())
    if not cleaned:
        return '""'
    if any(char.isspace() for char in cleaned) or any(ord(char) > 127 for char in cleaned):
        return f'"{cleaned}"'
    return cleaned


def dedupe(values) -> list[str]:
    seen: set[str] = set()
    unique: list[str] = []
    for value in values:
        normalized = " ".join(str(value).split())
        key = normalized.lower()
        if normalized and key not in seen:
            seen.add(key)
            unique.append(normalized)
    return unique


def normalize_text(value: str) -> str:
    return " ".join(value.lower().split())


def extract_match_terms(value: str) -> list[str]:
    quoted = re.findall(r'"([^"]+)"', value)
    bare = re.findall(r"[\w\u4e00-\u9fff][\w\-\u4e00-\u9fff]{2,}", value)
    stopwords = {
        "and",
        "or",
        "news",
        "satellite",
        "launch",
        "constellation",
        "broadband",
        "space",
    }
    return [
        term
        for term in [*quoted, *bare]
        if term.lower() not in stopwords and not term.startswith("{")
    ]


def stable_article_id(*, company_id: str, source_id: str, url: str, title: str) -> str:
    basis = f"{company_id}:{source_id}:{url or title}"
    return hashlib.sha256(basis.encode("utf-8")).hexdigest()[:16]


def url_with_query(base_url: str, params: dict[str, str | int]) -> str:
    return f"{base_url}?{urllib.parse.urlencode(params)}"
