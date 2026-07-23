from datetime import datetime, timedelta, timezone

from satellite_news.config import load_companies
from satellite_news.processing import QualityNewsProcessor
from satellite_news.schema import NewsItem, PipelineContext, SourceRecord, SourceType


def make_item(
    item_id: str,
    title: str,
    *,
    url: str | None = None,
    age_days: int = 0,
) -> NewsItem:
    return NewsItem(
        id=item_id,
        company_id="spacex",
        company_name="SpaceX",
        title=title,
        url=url or f"https://example.test/{item_id}",
        source=SourceRecord(
            source_id="rss_provider",
            source_type=SourceType.RSS,
            source_name="Example News",
            rank_group="media",
        ),
        published_at=datetime(2026, 7, 23, tzinfo=timezone.utc) - timedelta(days=age_days),
    )


def test_quality_gate_rejects_noise_old_items_and_near_duplicates():
    context = PipelineContext(
        run_id="quality-test",
        started_at=datetime(2026, 7, 23, tzinfo=timezone.utc),
        dry_run=False,
    )
    processor = QualityNewsProcessor(companies=load_companies())
    result = processor.process(
        items=(
            make_item(
                "good",
                "SpaceX launches new Starlink satellite batch",
                url="https://example.test/story?utm_source=rss&ref=home",
            ),
            make_item("duplicate", "SpaceX launches new Starlink satellite batch!"),
            make_item("noise", "NASA showcases a new wind tunnel"),
            make_item("old", "SpaceX launches Starlink satellite batch", age_days=90),
        ),
        context=context,
    )

    assert len(result) == 1
    assert result[0].url == "https://example.test/story"
    assert result[0].metadata["quality_decision"] == "published"
    assert result[0].metadata["event_id"]
    assert context.metadata["quality_gate"]["input_count"] == 4
    assert context.metadata["quality_gate"]["published_count"] == 1
    assert context.metadata["quality_gate"]["duplicate_count"] == 1
    assert context.metadata["quality_gate"]["rejected_count"] == 2


def test_quality_gate_routes_company_only_match_to_watchlist():
    context = PipelineContext(
        run_id="quality-watchlist",
        started_at=datetime(2026, 7, 23, tzinfo=timezone.utc),
        dry_run=False,
    )
    result = QualityNewsProcessor(companies=load_companies()).process(
        items=(make_item("company-only", "SpaceX announces executive appointment"),),
        context=context,
    )

    assert result == ()
    assert context.metadata["quality_gate"]["watchlist_count"] == 1


def test_quality_gate_publishes_primary_program_without_generic_context():
    context = PipelineContext(
        run_id="quality-program",
        started_at=datetime(2026, 7, 23, tzinfo=timezone.utc),
        dry_run=False,
    )
    result = QualityNewsProcessor(companies=load_companies()).process(
        items=(make_item("program-update", "Starlink deployments set a new monthly record"),),
        context=context,
    )

    assert [item.id for item in result] == ["program-update"]
    assert result[0].metadata["quality_reason_codes"] == ["title_program_match"]
