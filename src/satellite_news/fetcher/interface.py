"""Fetcher interface."""

from __future__ import annotations

from typing import Protocol

from satellite_news.schema import Company, NewsItem, PipelineContext, RawArticle, SourceConfig


class SourceFetcher(Protocol):
    def fetch_raw_articles(
        self,
        *,
        company: Company,
        source: SourceConfig,
        context: PipelineContext,
    ) -> tuple[RawArticle, ...]:
        """Fetch raw provider output for one company/source pair."""

    def fetch(
        self,
        *,
        company: Company,
        source: SourceConfig,
        context: PipelineContext,
    ) -> tuple[NewsItem, ...]:
        """Fetch raw candidate news items for one company/source pair."""


class NullFetcher:
    """No-op fetcher used by the architecture skeleton."""

    def fetch_raw_articles(
        self,
        *,
        company: Company,
        source: SourceConfig,
        context: PipelineContext,
    ) -> tuple[RawArticle, ...]:
        return ()

    def fetch(
        self,
        *,
        company: Company,
        source: SourceConfig,
        context: PipelineContext,
    ) -> tuple[NewsItem, ...]:
        return ()
