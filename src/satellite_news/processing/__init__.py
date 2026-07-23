"""Processing interfaces and placeholder implementations."""

from satellite_news.processing.events import build_event_timeline, classify_event_type
from satellite_news.processing.interface import NullProcessor, NewsProcessor
from satellite_news.processing.quality import QualityNewsProcessor

__all__ = [
    "NewsProcessor",
    "NullProcessor",
    "QualityNewsProcessor",
    "build_event_timeline",
    "classify_event_type",
]
