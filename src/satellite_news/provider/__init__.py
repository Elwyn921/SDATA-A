"""Provider interfaces for pluggable news sources."""

from __future__ import annotations

from typing import Callable

from satellite_news.fetcher.gdelt import GDELTHTTPTransport, GDELTFetcher
from satellite_news.provider.gdelt import GDELTProvider
from satellite_news.provider.brave_news import BraveNewsProvider
from satellite_news.provider.interface import (
    NewsProvider,
    NewsProviderRegistry,
    NullNewsProvider,
    ProviderResult,
)
from satellite_news.provider.newsapi import NewsAPIProvider
from satellite_news.provider.official_page import OfficialPageProvider
from satellite_news.provider.orchestrator import ProviderOrchestrator
from satellite_news.provider.rss import RSSProvider
from satellite_news.provider.serpapi import SerpApiGoogleNewsProvider
from satellite_news.provider.spaceflight_news import SpaceflightNewsAPIProvider


def build_default_provider_registry(
    *,
    progress: Callable[[str], None] | None = None,
) -> NewsProviderRegistry:
    return NewsProviderRegistry(
        (
            RSSProvider(),
            OfficialPageProvider(),
            SpaceflightNewsAPIProvider(),
            GDELTProvider(
                fetcher=GDELTFetcher(
                    transport=GDELTHTTPTransport(
                        timeout_seconds=20,
                        retries=0,
                        backoff_seconds=0.0,
                        rate_limit_seconds=0.0,
                        progress=progress,
                    )
                )
            ),
            SerpApiGoogleNewsProvider(),
            NewsAPIProvider(),
            BraveNewsProvider(),
        )
    )

__all__ = [
    "GDELTProvider",
    "BraveNewsProvider",
    "NewsProvider",
    "NewsProviderRegistry",
    "NewsAPIProvider",
    "NullNewsProvider",
    "OfficialPageProvider",
    "ProviderOrchestrator",
    "ProviderResult",
    "RSSProvider",
    "SerpApiGoogleNewsProvider",
    "SpaceflightNewsAPIProvider",
    "build_default_provider_registry",
]
