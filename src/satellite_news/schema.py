"""Shared data contracts for the satellite news intelligence pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Literal


SCHEMA_VERSION = "satellite_news.v1"


class PipelineStage(str, Enum):
    FETCH = "fetch"
    PROCESS = "process"
    SUMMARIZE = "summarize"
    EXPORT = "export"


class SourceType(str, Enum):
    OFFICIAL_SITE = "official_site"
    RSS = "rss"
    GDELT = "gdelt"
    SEARCH_API = "search_api"


Priority = Literal["low", "medium", "high", "critical"]


@dataclass(frozen=True)
class Company:
    id: str
    canonical_name: str
    aliases: tuple[str, ...] = ()
    country_or_region: str = ""
    sector_tags: tuple[str, ...] = ()
    enabled: bool = True
    priority: Priority = "medium"


@dataclass(frozen=True)
class SourceConfig:
    id: str
    type: SourceType
    rank_group: str
    enabled: bool = True
    description: str = ""
    options: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class SourceRecord:
    source_id: str
    source_type: SourceType
    source_name: str
    rank_group: str
    url: str | None = None
    collected_at: datetime | None = None
    raw_payload: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class NewsItem:
    id: str
    company_id: str
    company_name: str
    title: str
    url: str
    source: SourceRecord
    published_at: datetime | None = None
    language: str | None = None
    raw_text: str | None = None
    normalized_text: str | None = None
    tags: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RawArticle:
    id: str
    company_id: str
    company_name: str
    source_id: str
    source_type: SourceType
    title: str
    url: str
    published_at: datetime | None = None
    language: str | None = None
    raw_text: str | None = None
    raw_payload: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_news_item(self, source: SourceConfig, collected_at: datetime | None = None) -> NewsItem:
        source_record = SourceRecord(
            source_id=self.source_id,
            source_type=self.source_type,
            source_name=source.description or source.id,
            rank_group=source.rank_group,
            url=self.url,
            collected_at=collected_at,
            raw_payload=self.raw_payload,
        )
        return NewsItem(
            id=self.id,
            company_id=self.company_id,
            company_name=self.company_name,
            title=self.title,
            url=self.url,
            source=source_record,
            published_at=self.published_at,
            language=self.language,
            raw_text=self.raw_text,
            normalized_text=self.raw_text,
            metadata=self.metadata,
        )


@dataclass(frozen=True)
class NewsSummary:
    item_id: str
    company_id: str
    headline: str
    summary: str
    event_type: str | None = None
    importance_score: int | None = None
    priority: Priority = "medium"
    key_points: tuple[str, ...] = ()
    source_urls: tuple[str, ...] = ()
    model_metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ExportDocument:
    id: str
    format: Literal["markdown", "excel", "json", "html"]
    path: str
    title: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class PipelineContext:
    run_id: str
    started_at: datetime
    config_dir: str = "config"
    output_dir: str = "data/news/latest"
    dry_run: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class PipelineResult:
    run_id: str
    items: tuple[NewsItem, ...] = ()
    summaries: tuple[NewsSummary, ...] = ()
    exports: tuple[ExportDocument, ...] = ()
    warnings: tuple[str, ...] = ()
