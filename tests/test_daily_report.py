import json
from pathlib import Path

from satellite_news.reporting.daily_report import build_daily_report


def test_daily_report_skips_cleanly_without_openai_secret(tmp_path, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    pipeline_result_path = tmp_path / "pipeline_result.json"
    pipeline_result_path.write_text(
        json.dumps(
            {
                "run_id": "report-source-run",
                "generated_at": "2026-07-13T00:00:00Z",
                "items": [
                    {
                        "id": "item-1",
                        "company_id": "spacex",
                        "company_name": "SpaceX",
                        "title": "SpaceX launches a new Starlink batch",
                        "url": "https://example.test/starlink",
                        "published_at": "2026-07-12T00:00:00Z",
                        "fresh": True,
                        "stale": False,
                        "source": {
                            "source_id": "rss_provider",
                            "source_name": "Example RSS",
                            "source_type": "rss",
                        },
                    }
                ],
                "fetch_statuses": [
                    {
                        "company_id": "spacex",
                        "company_name": "SpaceX",
                        "provider_id": "rss_provider",
                        "source_type": "rss",
                        "status": "success",
                        "final_status": "success",
                        "item_count": 1,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    report, outputs = build_daily_report(
        pipeline_result_path=pipeline_result_path,
        latest_dir=tmp_path / "latest",
        publish_dir=tmp_path / "publish",
        archive_root=tmp_path / "archive",
    )

    assert report["generation_status"] == "skipped_no_secret"
    assert report["source_run_id"] == "report-source-run"
    assert report["total_items"] == 1
    assert len(report["industry_chain_sections"]) == 4
    assert outputs.latest_json.exists()
    assert outputs.latest_markdown.exists()
    assert outputs.published_json.exists()
    assert outputs.archived_json.exists()
    assert json.loads(Path(outputs.latest_json).read_text(encoding="utf-8")) == report
