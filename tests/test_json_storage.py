import json
from datetime import datetime, timezone

from satellite_news.schema import (
    NewsItem,
    PipelineContext,
    PipelineResult,
    SourceRecord,
    SourceType,
)
from satellite_news.storage import JsonFileStorage


def test_json_file_storage_writes_latest_and_archive_outputs(tmp_path):
    latest_dir = tmp_path / "data" / "news" / "latest"
    publish_dir = tmp_path / "docs" / "data" / "news"
    context = PipelineContext(
        run_id="json-run",
        started_at=datetime(2026, 6, 15, 8, 30, tzinfo=timezone.utc),
        output_dir=str(latest_dir),
        dry_run=False,
    )
    item = NewsItem(
        id="item-1",
        company_id="spacex",
        company_name="SpaceX",
        title="SpaceX launches satellite payload",
        url="https://example.test/spacex",
        source=SourceRecord(
            source_id="gdelt",
            source_type=SourceType.GDELT,
            source_name="GDELT",
            rank_group="wire",
            url="https://example.test/spacex",
            collected_at=context.started_at,
            raw_payload={"domain": "example.test"},
        ),
        published_at=datetime(2026, 6, 15, 7, 0, tzinfo=timezone.utc),
        language="English",
        raw_text="Launch update.",
        normalized_text="Launch update.",
        tags=("launch", "satellite"),
        metadata={"gdelt_query": "SpaceX satellite"},
    )
    result = PipelineResult(
        run_id="json-run",
        items=(item,),
        fetch_statuses=(
            {
                "company_id": "spacex",
                "company_name": "SpaceX",
                "source_id": "gdelt",
                "source_type": "gdelt",
                "status": "success",
                "item_count": 1,
                "query": "SpaceX satellite",
            },
        ),
    )

    JsonFileStorage(latest_dir=latest_dir, publish_dir=publish_dir).save_result(
        result=result,
        context=context,
    )

    latest_result = read_json(latest_dir / "pipeline_result.json")
    latest_items = read_json(latest_dir / "items.json")
    latest_statuses = read_json(latest_dir / "fetch_statuses.json")
    latest_manifest = read_json(latest_dir / "manifest.json")
    archive_run_dir = (
        tmp_path / "data" / "news" / "archive" / "runs" / "2026" / "06" / "15" / "json-run"
    )
    archive_index = read_json(tmp_path / "data" / "news" / "archive" / "index.json")
    published_result = read_json(publish_dir / "latest" / "pipeline_result.json")
    published_archive_index = read_json(publish_dir / "archive" / "index.json")

    assert latest_result["schema_version"] == "satellite_news.v1"
    assert latest_result["run_id"] == "json-run"
    assert latest_result["items"][0]["source"]["source_type"] == "gdelt"
    assert latest_result["items"][0]["published_at"] == "2026-06-15T07:00:00Z"
    assert latest_items["count"] == 1
    assert latest_statuses["fetch_statuses"][0]["error_message"] is None
    assert latest_statuses["fetch_statuses"][0]["metadata"] == {}
    assert latest_manifest["archive_path"] == archive_run_dir.as_posix()
    assert read_json(archive_run_dir / "pipeline_result.json")["run_id"] == "json-run"
    assert archive_index["latest_run_id"] == "json-run"
    assert archive_index["runs"][0]["companies"] == ["spacex"]
    assert published_result["run_id"] == "json-run"
    assert published_archive_index["latest_run_id"] == "json-run"


def test_json_file_storage_defaults_to_docs_publish_dir_for_repo_latest(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    latest_dir = "data/news/latest"
    publish_dir = tmp_path / "docs" / "data" / "news"
    context = PipelineContext(
        run_id="json-default-publish",
        started_at=datetime(2026, 6, 15, 8, 30, tzinfo=timezone.utc),
        output_dir=latest_dir,
        dry_run=False,
    )
    result = PipelineResult(run_id="json-default-publish")

    JsonFileStorage(latest_dir=latest_dir).save_result(result=result, context=context)

    assert read_json(publish_dir / "latest" / "pipeline_result.json")["run_id"] == (
        "json-default-publish"
    )


def read_json(path):
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)
