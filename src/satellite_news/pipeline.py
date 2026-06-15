"""Main flow for the GitHub-native satellite news pipeline."""

from __future__ import annotations

import argparse
import logging
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, TypeVar
from uuid import uuid4

from satellite_news.config import load_companies, load_sources
from satellite_news.exporter import NewsExporter, NullExporter
from satellite_news.fetcher import GDELTHTTPTransport, GDELTFetcher, NullFetcher, SourceFetcher
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
            fetch_statuses=tuple(context.metadata.get("fetch_statuses", ())),
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


def main(argv: tuple[str, ...] | None = None) -> PipelineResult:
    """CLI-safe entrypoint. Defaults to dry-run and does not call external APIs."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config-dir", type=Path, default=Path("config"))
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--dry-run", action=argparse.BooleanOptionalAction, default=True)
    args = parser.parse_args(argv)

    companies = load_companies(args.config_dir / "companies.yaml")
    sources = load_sources(args.config_dir / "sources.yaml")
    context = PipelineContext(
        run_id=args.run_id or str(uuid4()),
        started_at=datetime.now(timezone.utc),
        config_dir=str(args.config_dir),
        dry_run=args.dry_run,
    )
    result = Pipeline(fetcher=build_gdelt_fetcher(sources)).run(
        companies=companies,
        sources=sources,
        context=context,
    )
    print_result(result=result, companies=companies, dry_run=context.dry_run)
    return result


def build_gdelt_fetcher(sources: tuple[SourceConfig, ...]) -> GDELTFetcher:
    gdelt_source = next((source for source in sources if source.type.value == "gdelt"), None)
    options = gdelt_source.options.get("adapter_options", {}) if gdelt_source else {}
    transport = GDELTHTTPTransport(
        timeout_seconds=int(option_value(options, "timeout_seconds", 20)),
        retries=int(option_value(options, "retries", 2)),
        backoff_seconds=float(option_value(options, "backoff_seconds", 2.0)),
        rate_limit_seconds=float(option_value(options, "rate_limit_seconds", 3.0)),
        progress=lambda message: print(message, file=sys.stderr, flush=True),
    )
    return GDELTFetcher(transport=transport)


def option_value(options: dict[str, object], key: str, default: object) -> object:
    value = options.get(key, default)
    return default if value is None else value


def print_result(
    *,
    result: PipelineResult,
    companies: tuple[Company, ...],
    dry_run: bool,
) -> None:
    mode = "DRY RUN" if dry_run else "LIVE GDELT"
    print(f"Satellite news pipeline [{mode}] run_id={result.run_id}")
    print(f"Total NewsItem count: {len(result.items)}")
    status_rows = result.fetch_statuses
    for company in companies:
        if not company.enabled:
            continue
        company_items = tuple(item for item in result.items if item.company_id == company.id)
        status = fetch_status_for_company(status_rows, company.id)
        status_label = status.get("status", "no_results")
        print(
            f"\n## {company.canonical_name} ({company.id}) "
            f"- {status_label} - {len(company_items)} item(s)"
        )
        print(f"Query: {status.get('query') or '<not requested>'}")
        reason = status.get("reason")
        if reason:
            print(f"Reason: {reason}")
        if not company_items:
            continue
        for item in company_items[:10]:
            published = item.published_at.isoformat() if item.published_at else "unknown date"
            print(f"- [{published}] {item.title}")
            print(f"  {item.url}")


def fetch_status_for_company(status_rows: object, company_id: str) -> dict[str, object]:
    if not isinstance(status_rows, tuple):
        return {}
    for row in status_rows:
        if isinstance(row, dict) and row.get("company_id") == company_id:
            return row
    return {}


if __name__ == "__main__":
    main()
