"""Provider interface for GDELT, SerpApi, NewsAPI, RSS, and official-site sources.

Providers are plugin boundaries. They must return unified RawArticle objects and
must not leak provider-specific payloads beyond RawArticle.raw_payload/metadata.
Concrete network implementations belong to later agents, not this A1 layer.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from satellite_news.schema import Company, NewsProviderConfig, PipelineContext, RawArticle


@dataclass(frozen=True)
class ProviderResult:
    provider_id: str
    company_id: str
    articles: tuple[RawArticle, ...] = ()
    status: str = "not_implemented"
    should_fallback: bool = False
    warnings: tuple[str, ...] = ()
    metadata: dict[str, object] = field(default_factory=dict)


class NewsProvider(Protocol):
    @property
    def provider_id(self) -> str:
        """Stable provider id matching config/sources.yaml."""

    def fetch_raw_articles(
        self,
        *,
        company: Company,
        provider: NewsProviderConfig,
        context: PipelineContext,
    ) -> ProviderResult:
        """Return unified RawArticle rows for one company/provider pair."""


class NullNewsProvider:
    """No-op provider placeholder for architecture and import checks."""

    provider_id = "null"

    def fetch_raw_articles(
        self,
        *,
        company: Company,
        provider: NewsProviderConfig,
        context: PipelineContext,
    ) -> ProviderResult:
        return ProviderResult(
            provider_id=provider.id,
            company_id=company.id,
            status="placeholder",
            should_fallback=bool(provider.fallback.fallback_to),
        )


class NewsProviderRegistry:
    """In-memory provider registry used by future fetch orchestration."""

    def __init__(self, providers: tuple[NewsProvider, ...] = ()) -> None:
        self._providers = {provider.provider_id: provider for provider in providers}

    def get(self, provider_id: str) -> NewsProvider:
        return self._providers.get(provider_id, NullNewsProvider())

    def ids(self) -> tuple[str, ...]:
        return tuple(sorted(self._providers))
