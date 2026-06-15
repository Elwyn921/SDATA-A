"""Fetcher interfaces and minimal implementations."""

from satellite_news.fetcher.gdelt import GDELTHTTPTransport, GDELTFetcher, GDELTRequest
from satellite_news.fetcher.interface import NullFetcher, SourceFetcher
from satellite_news.provider import NewsProvider, NewsProviderRegistry, NullNewsProvider

__all__ = [
    "GDELTHTTPTransport",
    "GDELTFetcher",
    "GDELTRequest",
    "NewsProvider",
    "NewsProviderRegistry",
    "NullFetcher",
    "NullNewsProvider",
    "SourceFetcher",
]
