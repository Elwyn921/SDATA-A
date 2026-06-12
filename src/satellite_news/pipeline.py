"""Empty main flow for the GitHub-native satellite news pipeline."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable, TypeVar
from uuid import uuid4

from satellite_news.exporter import NewsExporter, NullExporter
from satellite_news.fetcher import NullFetcher, SourceFetcher
from satellite_news.llm import NewsSummarizer, NullSummarizer
from satellite_news.processing import NewsProcessor, NullProcessor
from satellite_news.schema import (
    Company,
    NewsItem,
    PipelineContext,
    PipelineResult,
    PipelineStage,
    SourceConfig,
)
from satellite_news.storage import NullStorage, PipelineStorage


LOGGER = logging.getLogger(__name__)
T = TypeVar("T")


class PipelineStageError(RuntimeError):
    """Raised when an architecture stage fails inside the orchestration boundary."""

    def __init__(self, stage: PipelineStage, message: str) -> None:
        super().__init__(message)
        self.stage = stage


@dataclass
class Pipeline:
    """Orchestrates fetch -> process -> summarize -> export without business logic."""

    fetcher: SourceFetcher = field(default_factory=NullFetcher)
    processor: NewsProcessor = field(default_factory=NullProcessor)
    summarizer: NewsSummarizer = field(default_factory=NullSummarizer)
    exporter: NewsExporter = field(default_factory=NullExporter)
    storage: PipelineStorage = field(default_factory=NullStorage)

    def run(
        self,
        *,
        companies: tuple[Company, ...] = (),
        sources: tuple[SourceConfig, ...] = (),
        context: PipelineContext | None = None,
    ) -> PipelineResult:
        context = context or PipelineContext(
            run_id=str(uuid4()),
            started_at=datetime.now(timezone.utc),
            dry_run=True,
        )

        LOGGER.info(
            "Starting satellite news pipeline run_id=%s dry_run=%s",
            context.run_id,
            context.dry_run,
        )
        fetched_items = self._run_stage(
            PipelineStage.FETCH,
            lambda: self._fetch(companies=companies, sources=sources, context=context),
        )
        processed_items = self._run_stage(
            PipelineStage.PROCESS,
            lambda: self.processor.process(items=fetched_items, context=context),
        )
        self.storage.save_items(items=processed_items, context=context)

        summaries = self._run_stage(
            PipelineStage.SUMMARIZE,
            lambda: self.summarizer.summarize(items=processed_items, context=context),
        )
        self.storage.save_summaries(summaries=summaries, context=context)

        exports = self._run_stage(
            PipelineStage.EXPORT,
            lambda: self.exporter.export(summaries=summaries, context=context),
        )
        result = PipelineResult(
            run_id=context.run_id,
            items=processed_items,
            summaries=summaries,
            exports=exports,
        )
        self.storage.save_result(result=result, context=context)
        LOGGER.info(
            "Finished satellite news pipeline run_id=%s items=%s summaries=%s exports=%s",
            context.run_id,
            len(processed_items),
            len(summaries),
            len(exports),
        )
        return result

    def _run_stage(self, stage: PipelineStage, operation: Callable[[], T]) -> T:
        try:
            return operation()
        except Exception as exc:
            LOGGER.exception("Pipeline stage failed: %s", stage.value)
            raise PipelineStageError(stage, f"{stage.value} stage failed") from exc

    def _fetch(
        self,
        *,
        companies: tuple[Company, ...],
        sources: tuple[SourceConfig, ...],
        context: PipelineContext,
    ) -> tuple[NewsItem, ...]:
        items: list[NewsItem] = []
        for company in companies:
            if not company.enabled:
                continue
            for source in sources:
                if not source.enabled:
                    continue
                items.extend(self.fetcher.fetch(company=company, source=source, context=context))
        return tuple(items)


def main() -> PipelineResult:
    """CLI-safe placeholder entrypoint. Does not load config or call APIs."""

    return Pipeline().run()


if __name__ == "__main__":
    main()
