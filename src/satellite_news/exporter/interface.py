"""Exporter interface for Markdown, JSON, Excel, HTML, or GitHub Pages targets."""

from __future__ import annotations

from typing import Protocol

from satellite_news.schema import ExportDocument, NewsSummary, PipelineContext


class NewsExporter(Protocol):
    def export(
        self,
        *,
        summaries: tuple[NewsSummary, ...],
        context: PipelineContext,
    ) -> tuple[ExportDocument, ...]:
        """Write summarized intelligence into one or more export formats."""


class NullExporter:
    """No-op exporter used by the architecture skeleton."""

    def export(
        self,
        *,
        summaries: tuple[NewsSummary, ...],
        context: PipelineContext,
    ) -> tuple[ExportDocument, ...]:
        return ()
