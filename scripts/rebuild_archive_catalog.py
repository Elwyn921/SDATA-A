"""Rebuild the durable catalog and event timeline from every archived run."""

from __future__ import annotations

import argparse
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from satellite_news.config import load_companies
from satellite_news.processing.events import build_event_timeline
from satellite_news.processing.quality import QualityNewsProcessor
from satellite_news.schema import NewsItem, PipelineContext, SourceRecord, SourceType
from satellite_news.storage.json_file import (
    ARTIFACT_VERSION,
    archive_item_key,
    compact_archive_item,
    daily_news_index_payload,
    isoformat,
    read_json_if_exists,
    serialize,
    write_json,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config-dir", type=Path, default=Path("config"))
    parser.add_argument("--data-root", type=Path, default=Path("data/news"))
    parser.add_argument("--publish-root", type=Path, default=Path("docs/data/news"))
    args = parser.parse_args()

    stats = rebuild_archive_catalog(
        config_dir=args.config_dir,
        data_root=args.data_root,
        publish_root=args.publish_root,
    )
    print(json.dumps(stats, ensure_ascii=False, sort_keys=True))


def rebuild_archive_catalog(
    *,
    config_dir: Path,
    data_root: Path,
    publish_root: Path | None,
) -> dict[str, Any]:
    archive_dir = data_root / "archive"
    latest_dir = data_root / "latest"
    run_files = sorted((archive_dir / "runs").rglob("items.json"))
    existing_catalog = read_json_if_exists(archive_dir / "catalog.json") or {}
    latest_result = read_json_if_exists(latest_dir / "pipeline_result.json") or {}
    generated_at = datetime.now(timezone.utc)
    run_id = str(latest_result.get("run_id") or "archive-rebuild")

    candidates: dict[str, dict[str, Any]] = {}
    sightings: dict[str, dict[str, str]] = {}
    for path in run_files:
        payload = read_json_if_exists(path) or {}
        observed_at = str(payload.get("generated_at") or "")
        observed_run_id = path.parent.name
        for row in payload.get("items", []):
            if not isinstance(row, dict):
                continue
            key = archive_item_key(row)
            candidate = candidates.get(key)
            if candidate is None or item_richness(row) > item_richness(candidate):
                candidates[key] = row
            source = row.get("source") if isinstance(row.get("source"), dict) else {}
            seen_at = str(source.get("collected_at") or observed_at or row.get("published_at") or "")
            record_sighting(
                sightings=sightings,
                key=key,
                seen_at=seen_at,
                run_id=observed_run_id,
            )

    for row in existing_catalog.get("items", []):
        if not isinstance(row, dict):
            continue
        key = archive_item_key(row)
        candidate = candidates.get(key)
        if candidate is None or item_richness(row) > item_richness(candidate):
            candidates[key] = row
        record_sighting(
            sightings=sightings,
            key=key,
            seen_at=str(row.get("archive_first_seen_at") or ""),
            run_id=str(row.get("archive_last_seen_run_id") or run_id),
        )
        record_sighting(
            sightings=sightings,
            key=key,
            seen_at=str(row.get("archive_last_seen_at") or ""),
            run_id=str(row.get("archive_last_seen_run_id") or run_id),
        )

    hydrated = tuple(
        item
        for row in candidates.values()
        if (item := hydrate_news_item(row)) is not None
    )
    context = PipelineContext(
        run_id=run_id,
        started_at=generated_at,
        dry_run=False,
        metadata={"archive_rebuild": True},
    )
    processed = QualityNewsProcessor(
        companies=load_companies(config_dir / "companies.yaml"),
        max_age_days=None,
    ).process(items=hydrated, context=context)

    archived_items = []
    for item in processed:
        serialized = serialize(item)
        archived = compact_archive_item(serialized)
        key = archive_item_key(archived)
        sighting = sightings.get(key, {})
        archived["archive_first_seen_at"] = sighting.get(
            "first_seen_at", isoformat(generated_at)
        )
        archived["archive_last_seen_at"] = sighting.get(
            "last_seen_at", isoformat(generated_at)
        )
        archived["archive_last_seen_run_id"] = sighting.get("last_seen_run_id", run_id)
        archived_items.append(archived)

    archived_items.sort(
        key=lambda item: (
            str(item.get("published_at") or ""),
            str(item.get("company_id") or ""),
            str(item.get("id") or ""),
        ),
        reverse=True,
    )
    daily_index = daily_news_index_payload(
        items=archived_items,
        run_id=run_id,
        generated_at=generated_at,
    )
    catalog = {
        "schema_version": "news_archive_catalog.v1",
        "artifact_version": ARTIFACT_VERSION,
        "generated_at": isoformat(generated_at),
        "latest_run_id": run_id,
        "item_count": len(archived_items),
        "date_count": daily_index["day_count"],
        "items": archived_items,
    }
    timeline = build_event_timeline(
        items=archived_items,
        run_id=run_id,
        generated_at=generated_at,
    )

    write_json(archive_dir / "catalog.json", catalog)
    write_json(latest_dir / "daily_index.json", daily_index)
    write_json(latest_dir / "event_timeline.json", timeline)
    if publish_root is not None:
        (publish_root / "archive").mkdir(parents=True, exist_ok=True)
        (publish_root / "latest").mkdir(parents=True, exist_ok=True)
        shutil.copy2(archive_dir / "catalog.json", publish_root / "archive" / "catalog.json")
        shutil.copy2(latest_dir / "daily_index.json", publish_root / "latest" / "daily_index.json")
        shutil.copy2(
            latest_dir / "event_timeline.json",
            publish_root / "latest" / "event_timeline.json",
        )

    quality = context.metadata.get("quality_gate", {})
    return {
        "run_file_count": len(run_files),
        "candidate_count": len(candidates),
        "hydrated_count": len(hydrated),
        "catalog_item_count": len(archived_items),
        "date_count": daily_index["day_count"],
        "event_count": timeline["event_count"],
        "quality_gate": {
            key: value
            for key, value in quality.items()
            if key != "rejected_samples"
        },
    }


def hydrate_news_item(row: dict[str, Any]) -> NewsItem | None:
    title = str(row.get("title") or "").strip()
    url = str(row.get("url") or "").strip()
    company_id = str(row.get("company_id") or "").strip()
    if not title or not company_id:
        return None
    source_row = row.get("source") if isinstance(row.get("source"), dict) else {}
    source_type_text = str(source_row.get("source_type") or "rss")
    try:
        source_type = SourceType(source_type_text)
    except ValueError:
        source_type = SourceType.RSS
    metadata = dict(row.get("metadata")) if isinstance(row.get("metadata"), dict) else {}
    quality = row.get("quality") if isinstance(row.get("quality"), dict) else {}
    metadata.update({key: value for key, value in quality.items() if key not in metadata})
    return NewsItem(
        id=str(row.get("id") or url or title),
        company_id=company_id,
        company_name=str(row.get("company_name") or company_id),
        title=title,
        url=url,
        source=SourceRecord(
            source_id=str(source_row.get("source_id") or "archive"),
            source_type=source_type,
            source_name=str(source_row.get("source_name") or "历史归档"),
            rank_group=str(source_row.get("rank_group") or "media"),
            provider_id=source_row.get("provider_id"),
            provider_priority=source_row.get("provider_priority"),
            url=source_row.get("url") or url,
            collected_at=parse_datetime(source_row.get("collected_at")),
            raw_payload=(
                dict(source_row.get("raw_payload"))
                if isinstance(source_row.get("raw_payload"), dict)
                else {}
            ),
        ),
        published_at=parse_datetime(row.get("published_at")),
        language=row.get("language"),
        raw_text=row.get("raw_text"),
        normalized_text=row.get("normalized_text"),
        tags=tuple(str(value) for value in row.get("tags", ()) or ()),
        metadata=metadata,
    )


def item_richness(row: dict[str, Any]) -> int:
    source = row.get("source") if isinstance(row.get("source"), dict) else {}
    metadata = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
    return (
        len(str(row.get("raw_text") or ""))
        + len(str(row.get("normalized_text") or ""))
        + len(metadata) * 20
        + len(source) * 10
    )


def record_sighting(
    *,
    sightings: dict[str, dict[str, str]],
    key: str,
    seen_at: str,
    run_id: str,
) -> None:
    if not seen_at:
        return
    row = sightings.setdefault(key, {})
    if not row.get("first_seen_at") or seen_at < row["first_seen_at"]:
        row["first_seen_at"] = seen_at
    if not row.get("last_seen_at") or seen_at > row["last_seen_at"]:
        row["last_seen_at"] = seen_at
        row["last_seen_run_id"] = run_id


def parse_datetime(value: object) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


if __name__ == "__main__":
    main()
