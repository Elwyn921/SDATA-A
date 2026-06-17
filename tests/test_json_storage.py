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


def test_json_file_storage_keeps_stale_company_items_when_current_run_is_empty(tmp_path):
    latest_dir = tmp_path / "data" / "news" / "latest"
    storage = JsonFileStorage(latest_dir=latest_dir)
    first_context = PipelineContext(
        run_id="first-run",
        started_at=datetime(2026, 6, 15, 8, 30, tzinfo=timezone.utc),
        output_dir=str(latest_dir),
        dry_run=False,
    )
    second_context = PipelineContext(
        run_id="second-run",
        started_at=datetime(2026, 6, 15, 9, 30, tzinfo=timezone.utc),
        output_dir=str(latest_dir),
        dry_run=False,
    )
    first_result = PipelineResult(
        run_id="first-run",
        items=(
            make_item("spacex-item-1", "spacex", "SpaceX"),
            make_item("blue-origin-item-1", "blue_origin", "Blue Origin"),
        ),
        fetch_statuses=(
            {"company_id": "spacex", "status": "success", "item_count": 1},
            {"company_id": "blue_origin", "status": "success", "item_count": 1},
        ),
    )
    second_result = PipelineResult(
        run_id="second-run",
        items=(make_item("spacex-item-2", "spacex", "SpaceX"),),
        fetch_statuses=(
            {"company_id": "spacex", "status": "success", "item_count": 1},
            {
                "company_id": "blue_origin",
                "status": "failed",
                "item_count": 0,
                "reason": "HTTP 429",
            },
        ),
    )

    storage.save_result(result=first_result, context=first_context)
    storage.save_result(result=second_result, context=second_context)

    latest_result = read_json(latest_dir / "pipeline_result.json")
    latest_items = read_json(latest_dir / "items.json")
    archive_result = read_json(
        tmp_path
        / "data"
        / "news"
        / "archive"
        / "runs"
        / "2026"
        / "06"
        / "15"
        / "second-run"
        / "pipeline_result.json"
    )
    blue_item = next(item for item in latest_result["items"] if item["company_id"] == "blue_origin")
    spacex_item = next(item for item in latest_result["items"] if item["company_id"] == "spacex")

    assert len(latest_result["items"]) == 2
    assert latest_items["count"] == 2
    assert spacex_item["fresh"] is True
    assert spacex_item["stale"] is False
    assert blue_item["fresh"] is False
    assert blue_item["stale"] is True
    assert blue_item["stale_from_run_id"] == "first-run"
    assert blue_item["metadata"]["stale_fallback_current_run_id"] == "second-run"
    assert latest_result["metadata"]["stale_fallback"]["fallback_company_ids"] == ["blue_origin"]
    assert latest_result["fetch_statuses"][1]["reason"] == "HTTP 429"
    assert len(archive_result["items"]) == 1
    assert archive_result["items"][0]["company_id"] == "spacex"


def test_json_file_storage_merges_partial_run_with_previous_latest(tmp_path):
    latest_dir = tmp_path / "data" / "news" / "latest"
    publish_dir = tmp_path / "docs" / "data" / "news"
    storage = JsonFileStorage(latest_dir=latest_dir, publish_dir=publish_dir)
    previous_context = PipelineContext(
        run_id="previous-full-run",
        started_at=datetime(2026, 6, 15, 8, 30, tzinfo=timezone.utc),
        output_dir=str(latest_dir),
        dry_run=False,
    )
    partial_context = PipelineContext(
        run_id="partial-spacex-gdelt",
        started_at=datetime(2026, 6, 15, 9, 30, tzinfo=timezone.utc),
        output_dir=str(latest_dir),
        dry_run=False,
        partial_run=True,
        scheduled_slot="slot-001",
        company_id="spacex",
        provider_id="gdelt_provider",
        max_gdelt_queries=1,
        merge_policy="latest_by_company",
    )
    previous_result = PipelineResult(
        run_id="previous-full-run",
        items=(
            make_item("spacex-old", "spacex", "SpaceX"),
            make_item("blue-origin-old", "blue_origin", "Blue Origin"),
            make_item("yuanxin-old", "yuanxin_satellite", "垣信卫星"),
            make_item("satnet-old", "china_satnet", "中国星网"),
        ),
        fetch_statuses=(
            {"company_id": "spacex", "status": "success", "item_count": 1},
            {"company_id": "blue_origin", "status": "success", "item_count": 1},
            {"company_id": "yuanxin_satellite", "status": "success", "item_count": 1},
            {"company_id": "china_satnet", "status": "success", "item_count": 1},
        ),
    )
    partial_result = PipelineResult(
        run_id="partial-spacex-gdelt",
        items=(make_item("spacex-new", "spacex", "SpaceX"),),
        fetch_statuses=(
            {
                "company_id": "spacex",
                "provider_id": "gdelt_provider",
                "status": "success",
                "item_count": 1,
            },
        ),
    )

    storage.save_result(result=previous_result, context=previous_context)
    previous_latest = read_json(latest_dir / "pipeline_result.json")
    storage.save_result(result=partial_result, context=partial_context)

    latest_result = read_json(latest_dir / "pipeline_result.json")
    published_result = read_json(publish_dir / "latest" / "pipeline_result.json")
    archive_result = read_json(
        tmp_path
        / "data"
        / "news"
        / "archive"
        / "runs"
        / "2026"
        / "06"
        / "15"
        / "partial-spacex-gdelt"
        / "pipeline_result.json"
    )
    items_by_company = {
        item["company_id"]: item
        for item in latest_result["items"]
    }
    fallback = latest_result["metadata"]["stale_fallback"]

    assert latest_result["partial_run"] is True
    assert latest_result["scheduled_slot"] == "slot-001"
    assert set(items_by_company) == {
        "spacex",
        "blue_origin",
        "yuanxin_satellite",
        "china_satnet",
    }
    assert items_by_company["spacex"]["id"] == "spacex-new"
    assert items_by_company["spacex"]["fresh"] is True
    assert items_by_company["blue_origin"]["stale"] is True
    assert items_by_company["blue_origin"]["fresh"] is False
    assert items_by_company["blue_origin"]["stale_reason"] == "partial_run_not_updated"
    assert items_by_company["blue_origin"]["stale_from_run_id"] == "previous-full-run"
    assert items_by_company["blue_origin"]["stale_as_of"] == previous_latest["generated_at"]
    assert fallback["partial_run"] is True
    assert fallback["scheduled_slot"] == "slot-001"
    assert fallback["updated_company_ids"] == ["spacex"]
    assert fallback["retained_company_ids"] == [
        "blue_origin",
        "china_satnet",
        "yuanxin_satellite",
    ]
    assert fallback["fresh_item_count"] == 1
    assert fallback["stale_item_count"] == 3
    assert fallback["previous_run_id"] == "previous-full-run"
    assert latest_result["fetch_statuses"][0]["provider_id"] == "gdelt_provider"
    assert published_result["items"] == latest_result["items"]
    assert len(archive_result["items"]) == 1
    assert archive_result["items"][0]["id"] == "spacex-new"


def make_item(item_id, company_id, company_name):
    return NewsItem(
        id=item_id,
        company_id=company_id,
        company_name=company_name,
        title=f"{company_name} update",
        url=f"https://example.test/{item_id}",
        source=SourceRecord(
            source_id="rss_provider",
            source_type=SourceType.RSS,
            source_name="RSS",
            rank_group="official",
        ),
    )


def read_json(path):
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)
