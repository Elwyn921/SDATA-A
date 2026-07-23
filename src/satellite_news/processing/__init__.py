"""Processing interfaces and placeholder implementations."""

from satellite_news.processing.interface import NullProcessor, NewsProcessor
from satellite_news.processing.quality import QualityNewsProcessor

__all__ = ["NewsProcessor", "NullProcessor", "QualityNewsProcessor"]
