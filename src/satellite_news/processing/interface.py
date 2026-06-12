"""Processing interface for normalization, dedupe, classification, and ranking."""

from __future__ import annotations

from typing import Protocol

from satellite_news.schema import NewsItem, PipelineContext


class NewsProcessor(Protocol):
    def process(
        self,
        *,
        items: tuple[NewsItem, ...],
        context: PipelineContext,
    ) -> tuple[NewsItem, ...]:
        """Return normalized and deduplicated news items."""


class NullProcessor:
    """Pass-through processor for import checks and orchestration tests."""

    def process(
        self,
        *,
        items: tuple[NewsItem, ...],
        context: PipelineContext,
    ) -> tuple[NewsItem, ...]:
        return items
