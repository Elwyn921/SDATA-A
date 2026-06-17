"""JSON file storage for pipeline outputs and long-lived news archives."""

from __future__ import annotations

import json
import shutil
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from satellite_news.schema import SCHEMA_VERSION, NewsSummary, PipelineContext, PipelineResult


ARTIFACT_VERSION = 1


class JsonFileStorage:
    """Persist pipeline outputs into latest and archive JSON directories."""

    def __init__(
        self,
        *,
        latest_dir: str | Path = "data/news/latest",
        archive_dir: str | Path | None = None,
        publish_dir: str | Path | None = None,
    ) -> None:
        self.latest_dir = Path(latest_dir)
        self.archive_dir = Path(archive_dir) if archive_dir else self.latest_dir.parent / "archive"
        self.publish_dir = resolve_publish_dir(self.latest_dir, publish_dir)

    def save_items(self, *, items, context: PipelineContext) -> None:
        now = utc_now()
        payload = {
            "schema_version": SCHEMA_VERSION,
            "artifact_version": ARTIFACT_VERSION,
            "run_id": context.run_id,
            "generated_at": isoformat(now),
            "count": len(items),
            "items": serialize(items),
        }
        self.latest_dir.mkdir(parents=True, exist_ok=True)
        write_json(self.latest_dir / "items.json", payload)

    def save_summaries(
        self,
        *,
        summaries: tuple[NewsSummary, ...],
        context: PipelineContext,
    ) -> None:
        now = utc_now()
        payload = {
            "schema_version": SCHEMA_VERSION,
            "artifact_version": ARTIFACT_VERSION,
            "run_id": context.run_id,
            "generated_at": isoformat(now),
            "count": len(summaries),
            "summaries": serialize(summaries),
        }
        self.latest_dir.mkdir(parents=True, exist_ok=True)
        write_json(self.latest_dir / "summaries.json", payload)

    def save_result(self, *, result: PipelineResult, context: PipelineContext) -> None:
        finished_at = utc_now()
        archive_run_dir = self.archive_run_dir(context=context)
        self.latest_dir.mkdir(parents=True, exist_ok=True)
        archive_run_dir.mkdir(parents=True, exist_ok=True)
        previous_latest = read_json_if_exists(self.latest_dir / "pipeline_result.json")

        files = {
            "pipeline_result": "pipeline_result.json",
            "items": "items.json",
            "summaries": "summaries.json",
            "fetch_statuses": "fetch_statuses.json",
            "run_metadata": "run_metadata.json",
            "manifest": "manifest.json",
        }
        pipeline_result = pipeline_result_payload(
            result=result,
            context=context,
            finished_at=finished_at,
        )
        latest_pipeline_result = apply_stale_fallback(
            current=pipeline_result,
            previous=previous_latest,
            context=context,
            generated_at=finished_at,
        )
        items = items_payload_from_pipeline_result(
            pipeline_result=latest_pipeline_result,
            context=context,
            generated_at=finished_at,
        )
        summaries = summaries_payload(result=result, context=context, generated_at=finished_at)
        fetch_statuses = fetch_statuses_payload(
            result=result,
            context=context,
            generated_at=finished_at,
        )
        run_metadata = run_metadata_payload(
            result=result,
            context=context,
            finished_at=finished_at,
        )
        latest_run_metadata = run_metadata_from_pipeline_result(
            run_metadata=run_metadata,
            pipeline_result=latest_pipeline_result,
        )
        manifest = manifest_payload(
            context=context,
            generated_at=finished_at,
            archive_run_dir=archive_run_dir,
            files=files,
        )

        payloads = {
            files["pipeline_result"]: latest_pipeline_result,
            files["items"]: items,
            files["summaries"]: summaries,
            files["fetch_statuses"]: fetch_statuses,
            files["run_metadata"]: latest_run_metadata,
            files["manifest"]: manifest,
        }
        for filename, payload in payloads.items():
            write_json(self.latest_dir / filename, payload)
        archive_payloads = {
            files["pipeline_result"]: pipeline_result,
            files["items"]: items_payload(result=result, context=context, generated_at=finished_at),
            files["summaries"]: summaries,
            files["fetch_statuses"]: fetch_statuses,
            files["run_metadata"]: run_metadata,
            files["manifest"]: manifest,
        }
        for filename, payload in archive_payloads.items():
            write_json(archive_run_dir / filename, payload)
        update_archive_index(
            archive_dir=self.archive_dir,
            result=result,
            context=context,
            archive_run_dir=archive_run_dir,
            finished_at=finished_at,
        )
        if self.publish_dir:
            sync_publish_outputs(
                publish_dir=self.publish_dir,
                latest_dir=self.latest_dir,
                archive_dir=self.archive_dir,
                files=files,
            )

    def archive_run_dir(self, *, context: PipelineContext) -> Path:
        started_at = ensure_aware_utc(context.started_at)
        return (
            self.archive_dir
            / "runs"
            / f"{started_at.year:04d}"
            / f"{started_at.month:02d}"
            / f"{started_at.day:02d}"
            / context.run_id
        )


def pipeline_result_payload(
    *,
    result: PipelineResult,
    context: PipelineContext,
    finished_at: datetime,
) -> dict[str, Any]:
    items = serialize(result.items)
    if isinstance(items, list):
        for item in items:
            if isinstance(item, dict):
                item.setdefault("run_id", result.run_id)
    return {
        "schema_version": SCHEMA_VERSION,
        "artifact_version": ARTIFACT_VERSION,
        "run_id": result.run_id,
        "started_at": isoformat(context.started_at),
        "finished_at": isoformat(finished_at),
        "generated_at": isoformat(finished_at),
        "dry_run": context.dry_run,
        "partial_run": context.partial_run,
        "scheduled_slot": context.scheduled_slot,
        "company_id": context.company_id,
        "provider_id": context.provider_id,
        "max_gdelt_queries": context.max_gdelt_queries,
        "merge_policy": context.merge_policy,
        "items": items,
        "summaries": serialize(result.summaries),
        "exports": serialize(result.exports),
        "fetch_statuses": normalize_fetch_statuses(result.fetch_statuses),
        "warnings": list(result.warnings),
    }


def items_payload(
    *,
    result: PipelineResult,
    context: PipelineContext,
    generated_at: datetime,
) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "artifact_version": ARTIFACT_VERSION,
        "run_id": context.run_id,
        "generated_at": isoformat(generated_at),
        "count": len(result.items),
        "items": serialize(result.items),
    }


def items_payload_from_pipeline_result(
    *,
    pipeline_result: dict[str, Any],
    context: PipelineContext,
    generated_at: datetime,
) -> dict[str, Any]:
    items = pipeline_result.get("items", [])
    if not isinstance(items, list):
        items = []
    return {
        "schema_version": SCHEMA_VERSION,
        "artifact_version": ARTIFACT_VERSION,
        "run_id": context.run_id,
        "generated_at": isoformat(generated_at),
        "count": len(items),
        "items": items,
    }


def summaries_payload(
    *,
    result: PipelineResult,
    context: PipelineContext,
    generated_at: datetime,
) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "artifact_version": ARTIFACT_VERSION,
        "run_id": context.run_id,
        "generated_at": isoformat(generated_at),
        "count": len(result.summaries),
        "summaries": serialize(result.summaries),
    }


def fetch_statuses_payload(
    *,
    result: PipelineResult,
    context: PipelineContext,
    generated_at: datetime,
) -> dict[str, Any]:
    statuses = normalize_fetch_statuses(result.fetch_statuses)
    return {
        "schema_version": SCHEMA_VERSION,
        "artifact_version": ARTIFACT_VERSION,
        "run_id": context.run_id,
        "generated_at": isoformat(generated_at),
        "count": len(statuses),
        "fetch_statuses": statuses,
    }


def apply_stale_fallback(
    *,
    current: dict[str, Any],
    previous: dict[str, Any] | None,
    context: PipelineContext,
    generated_at: datetime,
) -> dict[str, Any]:
    if not previous:
        return mark_fresh_items(current)

    if context.partial_run:
        return apply_partial_run_merge(
            current=current,
            previous=previous,
            context=context,
            generated_at=generated_at,
        )

    return apply_full_run_stale_fallback(
        current=current,
        previous=previous,
        generated_at=generated_at,
    )


def apply_full_run_stale_fallback(
    *,
    current: dict[str, Any],
    previous: dict[str, Any],
    generated_at: datetime,
) -> dict[str, Any]:
    current_items = list(current.get("items", []))
    previous_items = [
        item
        for item in previous.get("items", [])
        if isinstance(item, dict) and item.get("company_id")
    ]
    previous_by_company = group_items_by_company(previous_items)
    current_by_company = group_items_by_company(
        item for item in current_items if isinstance(item, dict) and item.get("company_id")
    )
    companies = set(previous_by_company) | set(current_by_company) | status_company_ids(current)

    merged_items = []
    fallback_companies = []
    for company_id in sorted(companies):
        company_items = current_by_company.get(company_id, [])
        if company_items:
            merged_items.extend(mark_items_fresh(company_items))
            continue

        stale_items = previous_by_company.get(company_id, [])
        if stale_items:
            fallback_companies.append(company_id)
            merged_items.extend(
                mark_items_stale(
                    items=stale_items,
                    current_run_id=str(current.get("run_id", "")),
                    generated_at=generated_at,
                    stale_reason="current_run_company_empty",
                    stale_as_of=generated_at,
                )
            )

    if not companies:
        merged_items = mark_items_fresh(current_items)

    merged = dict(current)
    merged["items"] = merged_items
    metadata = dict(merged.get("metadata", {})) if isinstance(merged.get("metadata"), dict) else {}
    metadata["stale_fallback"] = {
        "enabled": True,
        "fallback_company_ids": fallback_companies,
        "fresh_item_count": sum(1 for item in merged_items if not item.get("stale", False)),
        "stale_item_count": sum(1 for item in merged_items if item.get("stale", False)),
        "previous_run_id": previous.get("run_id"),
        "partial_run": False,
    }
    merged["metadata"] = metadata
    return merged


def apply_partial_run_merge(
    *,
    current: dict[str, Any],
    previous: dict[str, Any],
    context: PipelineContext,
    generated_at: datetime,
) -> dict[str, Any]:
    current_items = [
        item
        for item in current.get("items", [])
        if isinstance(item, dict) and item.get("company_id")
    ]
    previous_items = [
        item
        for item in previous.get("items", [])
        if isinstance(item, dict) and item.get("company_id")
    ]
    current_by_company = group_items_by_company(current_items)
    previous_by_company = group_items_by_company(previous_items)
    updated_company_ids = updated_company_ids_for_partial_run(
        current=current,
        context=context,
    )
    fresh_updated_company_ids = {
        company_id
        for company_id in updated_company_ids
        if current_by_company.get(company_id)
    }
    empty_updated_company_ids = {
        company_id
        for company_id in updated_company_ids
        if not current_by_company.get(company_id)
    }
    retained_company_ids = sorted(set(previous_by_company) - updated_company_ids)
    previous_generated_at = parse_datetime_string(previous.get("generated_at"))

    merged_items = []
    for company_id in sorted(fresh_updated_company_ids):
        merged_items.extend(mark_items_fresh(current_by_company.get(company_id, [])))
    for company_id in sorted(empty_updated_company_ids):
        stale_items = previous_by_company.get(company_id, [])
        if stale_items:
            merged_items.extend(
                mark_items_stale(
                    items=stale_items,
                    current_run_id=str(current.get("run_id", "")),
                    generated_at=generated_at,
                    stale_reason="partial_run_company_empty",
                    stale_as_of=previous_generated_at or generated_at,
                )
            )
    for company_id in retained_company_ids:
        merged_items.extend(
            mark_items_stale(
                items=previous_by_company[company_id],
                current_run_id=str(current.get("run_id", "")),
                generated_at=generated_at,
                stale_reason="partial_run_not_updated",
                stale_as_of=previous_generated_at or generated_at,
            )
        )

    merged = dict(current)
    merged["items"] = merged_items
    metadata = dict(merged.get("metadata", {})) if isinstance(merged.get("metadata"), dict) else {}
    metadata["stale_fallback"] = {
        "enabled": True,
        "partial_run": True,
        "scheduled_slot": context.scheduled_slot,
        "updated_company_ids": sorted(fresh_updated_company_ids),
        "retained_company_ids": retained_company_ids,
        "empty_updated_company_ids": sorted(empty_updated_company_ids),
        "fallback_company_ids": sorted(set(retained_company_ids) | empty_updated_company_ids),
        "fresh_item_count": sum(1 for item in merged_items if not item.get("stale", False)),
        "stale_item_count": sum(1 for item in merged_items if item.get("stale", False)),
        "previous_run_id": previous.get("run_id"),
        "provider_id": context.provider_id,
        "company_id": context.company_id,
        "company_ids": sorted(context_filter_values(context, "company_ids", context.company_id)),
        "provider_ids": sorted(context_filter_values(context, "provider_ids", context.provider_id)),
        "merge_policy": context.merge_policy,
    }
    merged["metadata"] = metadata
    return merged


def mark_fresh_items(pipeline_result: dict[str, Any]) -> dict[str, Any]:
    marked = dict(pipeline_result)
    marked["items"] = mark_items_fresh(
        item for item in pipeline_result.get("items", []) if isinstance(item, dict)
    )
    return marked


def mark_items_fresh(items) -> list[dict[str, Any]]:
    fresh_items = []
    for item in items:
        marked = dict(item)
        marked["fresh"] = True
        marked["stale"] = False
        marked.pop("stale_reason", None)
        marked.pop("stale_from_run_id", None)
        marked.pop("stale_as_of", None)
        fresh_items.append(marked)
    return fresh_items


def mark_items_stale(
    *,
    items: list[dict[str, Any]],
    current_run_id: str,
    generated_at: datetime,
    stale_reason: str,
    stale_as_of: datetime,
) -> list[dict[str, Any]]:
    stale_items = []
    for item in items:
        marked = dict(item)
        marked["fresh"] = False
        marked["stale"] = True
        marked["stale_reason"] = stale_reason
        marked["stale_from_run_id"] = item.get("stale_from_run_id") or item.get("run_id")
        marked["stale_as_of"] = isoformat(stale_as_of)
        metadata = (
            dict(marked.get("metadata", {}))
            if isinstance(marked.get("metadata"), dict)
            else {}
        )
        metadata["stale_fallback_current_run_id"] = current_run_id
        marked["metadata"] = metadata
        stale_items.append(marked)
    return stale_items


def group_items_by_company(items) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for item in items:
        company_id = item.get("company_id")
        if company_id:
            grouped.setdefault(str(company_id), []).append(item)
    return grouped


def company_item_counts(items: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in items:
        company_id = item.get("company_id")
        if company_id:
            counts[str(company_id)] = counts.get(str(company_id), 0) + 1
    return counts


def status_company_ids(pipeline_result: dict[str, Any]) -> set[str]:
    ids = set()
    for status in pipeline_result.get("fetch_statuses", []):
        if isinstance(status, dict) and status.get("company_id"):
            ids.add(str(status["company_id"]))
    return ids


def updated_company_ids_for_partial_run(
    *,
    current: dict[str, Any],
    context: PipelineContext,
) -> set[str]:
    ids = {str(company_id) for company_id in status_company_ids(current)}
    ids.update(
        str(item["company_id"])
        for item in current.get("items", [])
        if isinstance(item, dict) and item.get("company_id")
    )
    ids.update(context_filter_values(context, "company_ids", context.company_id))
    return ids


def context_filter_values(
    context: PipelineContext,
    metadata_key: str,
    fallback_value: str | None,
) -> set[str]:
    metadata_values = context.metadata.get(metadata_key)
    if isinstance(metadata_values, (list, tuple)):
        return {str(value) for value in metadata_values if value}
    if not fallback_value:
        return set()
    return {value.strip() for value in fallback_value.split(",") if value.strip()}


def parse_datetime_string(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def run_metadata_payload(
    *,
    result: PipelineResult,
    context: PipelineContext,
    finished_at: datetime,
) -> dict[str, Any]:
    statuses = normalize_fetch_statuses(result.fetch_statuses)
    return {
        "schema_version": SCHEMA_VERSION,
        "artifact_version": ARTIFACT_VERSION,
        "run_id": context.run_id,
        "started_at": isoformat(context.started_at),
        "finished_at": isoformat(finished_at),
        "generated_at": isoformat(finished_at),
        "dry_run": context.dry_run,
        "config_dir": context.config_dir,
        "output_dir": context.output_dir,
        "item_count": len(result.items),
        "summary_count": len(result.summaries),
        "export_count": len(result.exports),
        "fetch_status_count": len(statuses),
        "companies": company_rollups(result=result, statuses=statuses),
        "warnings": list(result.warnings),
    }


def manifest_payload(
    *,
    context: PipelineContext,
    generated_at: datetime,
    archive_run_dir: Path,
    files: dict[str, str],
) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "artifact_version": ARTIFACT_VERSION,
        "run_id": context.run_id,
        "generated_at": isoformat(generated_at),
        "archive_path": archive_run_dir.as_posix(),
        "files": files,
    }


def run_metadata_from_pipeline_result(
    *,
    run_metadata: dict[str, Any],
    pipeline_result: dict[str, Any],
) -> dict[str, Any]:
    updated = dict(run_metadata)
    items = pipeline_result.get("items", [])
    if isinstance(items, list):
        updated["item_count"] = len(items)
        updated["company_item_counts"] = company_item_counts(items)
        updated["stale_item_count"] = sum(1 for item in items if item.get("stale"))
        updated["fresh_item_count"] = sum(1 for item in items if not item.get("stale"))
    metadata = (
        dict(updated.get("metadata", {}))
        if isinstance(updated.get("metadata"), dict)
        else {}
    )
    metadata["latest_is_stale_safe"] = True
    updated["metadata"] = metadata
    return updated


def update_archive_index(
    *,
    archive_dir: Path,
    result: PipelineResult,
    context: PipelineContext,
    archive_run_dir: Path,
    finished_at: datetime,
) -> None:
    archive_dir.mkdir(parents=True, exist_ok=True)
    index_path = archive_dir / "index.json"
    if index_path.exists():
        with index_path.open("r", encoding="utf-8") as handle:
            index = json.load(handle)
    else:
        index = {
            "schema_version": SCHEMA_VERSION,
            "artifact_version": ARTIFACT_VERSION,
            "generated_at": isoformat(finished_at),
            "latest_run_id": None,
            "runs": [],
        }

    run_entry = archive_index_entry(
        result=result,
        context=context,
        archive_run_dir=archive_run_dir,
        finished_at=finished_at,
    )
    runs = []
    for row in index.get("runs", []):
        if isinstance(row, dict) and row.get("run_id") != result.run_id:
            runs.append(row)
    runs.append(run_entry)
    runs.sort(key=lambda row: str(row.get("started_at", "")), reverse=True)

    index.update(
        {
            "schema_version": SCHEMA_VERSION,
            "artifact_version": ARTIFACT_VERSION,
            "generated_at": isoformat(finished_at),
            "latest_run_id": result.run_id,
            "runs": runs,
        }
    )
    write_json(index_path, index)


def archive_index_entry(
    *,
    result: PipelineResult,
    context: PipelineContext,
    archive_run_dir: Path,
    finished_at: datetime,
) -> dict[str, Any]:
    statuses = normalize_fetch_statuses(result.fetch_statuses)
    return {
        "run_id": result.run_id,
        "started_at": isoformat(context.started_at),
        "finished_at": isoformat(finished_at),
        "archive_path": archive_run_dir.as_posix(),
        "item_count": len(result.items),
        "fetch_status_count": len(statuses),
        "dry_run": context.dry_run,
        "status": run_status(statuses),
        "companies": sorted(company_ids(result=result, statuses=statuses)),
    }


def resolve_publish_dir(
    latest_dir: Path,
    publish_dir: str | Path | None,
) -> Path | None:
    if publish_dir:
        return Path(publish_dir)
    if latest_dir == Path("data/news/latest"):
        return Path("docs/data/news")
    return None


def sync_publish_outputs(
    *,
    publish_dir: Path,
    latest_dir: Path,
    archive_dir: Path,
    files: dict[str, str],
) -> None:
    publish_latest = publish_dir / "latest"
    publish_archive = publish_dir / "archive"
    publish_latest.mkdir(parents=True, exist_ok=True)
    publish_archive.mkdir(parents=True, exist_ok=True)

    for filename in files.values():
        source = latest_dir / filename
        if source.exists():
            shutil.copy2(source, publish_latest / filename)

    archive_index = archive_dir / "index.json"
    if archive_index.exists():
        shutil.copy2(archive_index, publish_archive / "index.json")


def company_rollups(
    *,
    result: PipelineResult,
    statuses: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    company_names = {item.company_id: item.company_name for item in result.items}
    for status in statuses:
        company_id = status.get("company_id")
        company_name = status.get("company_name")
        if company_id and company_name:
            company_names[str(company_id)] = str(company_name)

    rollups = []
    for company_id in sorted(company_ids(result=result, statuses=statuses)):
        item_count = sum(1 for item in result.items if item.company_id == company_id)
        company_statuses = [
            str(status.get("status", ""))
            for status in statuses
            if status.get("company_id") == company_id
        ]
        rollups.append(
            {
                "company_id": company_id,
                "company_name": company_names.get(company_id, ""),
                "item_count": item_count,
                "status": company_status(company_statuses),
            }
        )
    return rollups


def company_ids(*, result: PipelineResult, statuses: list[dict[str, Any]]) -> set[str]:
    ids = {item.company_id for item in result.items}
    ids.update(str(status["company_id"]) for status in statuses if status.get("company_id"))
    return ids


def company_status(statuses: list[str]) -> str:
    real_statuses = [status for status in statuses if status]
    if not real_statuses:
        return "no_results"
    unique = set(real_statuses)
    if len(unique) == 1:
        return real_statuses[0]
    if "failed" in unique and unique <= {"failed", "no_results", "dry_run"}:
        return "failed"
    return "mixed"


def run_status(statuses: list[dict[str, Any]]) -> str:
    labels = {str(status.get("status", "")) for status in statuses}
    labels.discard("")
    if not labels:
        return "success"
    if labels <= {"success", "no_results", "dry_run"}:
        return "success"
    if labels == {"failed"}:
        return "failed"
    return "partial"


def normalize_fetch_statuses(statuses: tuple[dict[str, Any], ...]) -> list[dict[str, Any]]:
    normalized = []
    for status in statuses:
        row = dict(serialize(status))
        row.setdefault("company_id", "")
        row.setdefault("company_name", "")
        row.setdefault("source_id", "")
        row.setdefault("source_type", "")
        row.setdefault("status", "")
        row.setdefault("query", None)
        row.setdefault("item_count", 0)
        row.setdefault("started_at", None)
        row.setdefault("finished_at", None)
        row.setdefault("error_type", None)
        row.setdefault("error_message", None)
        row.setdefault("reason", None)
        row.setdefault("metadata", {})
        normalized.append(row)
    return normalized


def serialize(value: Any) -> Any:
    if is_dataclass(value) and not isinstance(value, type):
        return serialize(asdict(value))
    if isinstance(value, datetime):
        return isoformat(value)
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Path):
        return value.as_posix()
    if isinstance(value, tuple):
        return [serialize(item) for item in value]
    if isinstance(value, list):
        return [serialize(item) for item in value]
    if isinstance(value, dict):
        return {str(key): serialize(item) for key, item in value.items()}
    return value


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(f"{path.suffix}.tmp")
    with temp_path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")
    shutil.move(str(temp_path), str(path))


def read_json_if_exists(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    return payload if isinstance(payload, dict) else None


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def isoformat(value: datetime) -> str:
    return ensure_aware_utc(value).isoformat().replace("+00:00", "Z")


def ensure_aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
