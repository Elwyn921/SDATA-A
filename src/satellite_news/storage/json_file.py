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
        items = items_payload(result=result, context=context, generated_at=finished_at)
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
        manifest = manifest_payload(
            context=context,
            generated_at=finished_at,
            archive_run_dir=archive_run_dir,
            files=files,
        )

        payloads = {
            files["pipeline_result"]: pipeline_result,
            files["items"]: items,
            files["summaries"]: summaries,
            files["fetch_statuses"]: fetch_statuses,
            files["run_metadata"]: run_metadata,
            files["manifest"]: manifest,
        }
        for filename, payload in payloads.items():
            write_json(self.latest_dir / filename, payload)
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
    return {
        "schema_version": SCHEMA_VERSION,
        "artifact_version": ARTIFACT_VERSION,
        "run_id": result.run_id,
        "started_at": isoformat(context.started_at),
        "finished_at": isoformat(finished_at),
        "generated_at": isoformat(finished_at),
        "dry_run": context.dry_run,
        "items": serialize(result.items),
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


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def isoformat(value: datetime) -> str:
    return ensure_aware_utc(value).isoformat().replace("+00:00", "Z")


def ensure_aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
