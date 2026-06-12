"""Fetcher interfaces and minimal implementations."""

from satellite_news.fetcher.gdelt import GDELTHTTPTransport, GDELTFetcher, GDELTRequest
from satellite_news.fetcher.interface import NullFetcher, SourceFetcher

__all__ = ["GDELTHTTPTransport", "GDELTFetcher", "GDELTRequest", "NullFetcher", "SourceFetcher"]
