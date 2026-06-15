"""Satellite news intelligence pipeline package."""

from satellite_news.pipeline import Pipeline, PipelineStageError
from satellite_news.schema import (
    NewsItem,
    NewsProviderConfig,
    NewsSummary,
    PipelineResult,
    RawArticle,
    SourceRecord,
)

__all__ = [
    "NewsItem",
    "NewsProviderConfig",
    "NewsSummary",
    "Pipeline",
    "PipelineStageError",
    "PipelineResult",
    "RawArticle",
    "SourceRecord",
]
