"""LLM summarization interface. No provider-specific calls belong here."""

from __future__ import annotations

from typing import Protocol

from satellite_news.schema import NewsItem, NewsSummary, PipelineContext


class NewsSummarizer(Protocol):
    def summarize(
        self,
        *,
        items: tuple[NewsItem, ...],
        context: PipelineContext,
    ) -> tuple[NewsSummary, ...]:
        """Summarize processed news items into structured intelligence records."""


class NullSummarizer:
    """No-op summarizer used until an LLM agent provides an implementation."""

    def summarize(
        self,
        *,
        items: tuple[NewsItem, ...],
        context: PipelineContext,
    ) -> tuple[NewsSummary, ...]:
        return ()
