"""Storage interface for local files, GitHub artifacts, or future object stores."""

from __future__ import annotations

from typing import Protocol

from satellite_news.schema import NewsItem, NewsSummary, PipelineContext, PipelineResult


class PipelineStorage(Protocol):
    def save_items(
        self,
        *,
        items: tuple[NewsItem, ...],
        context: PipelineContext,
    ) -> None:
        """Persist processed items for audit and downstream reuse."""

    def save_summaries(
        self,
        *,
        summaries: tuple[NewsSummary, ...],
        context: PipelineContext,
    ) -> None:
        """Persist summaries before export."""

    def save_result(
        self,
        *,
        result: PipelineResult,
        context: PipelineContext,
    ) -> None:
        """Persist the final pipeline result manifest."""


class NullStorage:
    """No-op storage used until a storage agent adds concrete persistence."""

    def save_items(
        self,
        *,
        items: tuple[NewsItem, ...],
        context: PipelineContext,
    ) -> None:
        return None

    def save_summaries(
        self,
        *,
        summaries: tuple[NewsSummary, ...],
        context: PipelineContext,
    ) -> None:
        return None

    def save_result(
        self,
        *,
        result: PipelineResult,
        context: PipelineContext,
    ) -> None:
        return None
