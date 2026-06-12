"""Processing interfaces and placeholder implementations."""

from satellite_news.processing.interface import NullProcessor, NewsProcessor

__all__ = ["NewsProcessor", "NullProcessor"]
