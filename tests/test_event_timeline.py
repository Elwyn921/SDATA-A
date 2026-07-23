from datetime import datetime, timezone

from satellite_news.processing.events import build_event_timeline, classify_event_type


def test_event_classifier_covers_p1_categories():
    assert classify_event_type("蓝箭航天朱雀三号完成发射") == "launch"
    assert classify_event_type("星河动力完成D轮融资") == "financing"
    assert classify_event_type("中国星网获得新订单合同") == "order"
    assert classify_event_type("监管部门批准卫星通信牌照") == "regulation"
    assert classify_event_type("商业航天概念股股价涨停") == "market"


def test_event_timeline_clusters_scattered_reports():
    items = [
        make_item(
            "finance-1",
            "星河动力完成D轮融资",
            "2026-07-20T08:00:00Z",
            "媒体甲",
            "financing",
        ),
        make_item(
            "finance-2",
            "星河动力D轮融资完成，募资数亿元",
            "2026-07-21T09:00:00Z",
            "媒体乙",
            "financing",
        ),
        make_item(
            "market-1",
            "星河动力概念股股价大涨",
            "2026-07-21T10:00:00Z",
            "财经媒体",
            "market",
        ),
    ]

    timeline = build_event_timeline(
        items=items,
        run_id="timeline-test",
        generated_at=datetime(2026, 7, 23, tzinfo=timezone.utc),
    )

    assert timeline["event_count"] == 2
    assert timeline["article_count"] == 3
    assert timeline["embedded_article_count"] == 3
    assert timeline["inferred_date_article_count"] == 0
    assert timeline["is_complete"] is True
    assert timeline["earliest_at"] == "2026-07-20T08:00:00Z"
    assert timeline["latest_at"] == "2026-07-21T10:00:00Z"
    assert timeline["event_type_counts"] == {"financing": 1, "market": 1}
    financing = next(event for event in timeline["events"] if event["event_type"] == "financing")
    assert financing["article_count"] == 2
    assert financing["source_count"] == 2
    assert len(financing["articles"]) == 2


def test_event_timeline_keeps_distinct_same_day_events_separate():
    items = [
        make_item(
            "launch-1",
            "星河动力谷神星一号完成海上发射",
            "2026-07-20T08:00:00Z",
            "媒体甲",
            "launch",
        ),
        make_item(
            "launch-2",
            "星河动力智神星二号发动机完成静态点火",
            "2026-07-20T10:00:00Z",
            "媒体乙",
            "launch",
        ),
    ]

    timeline = build_event_timeline(
        items=items,
        run_id="same-day-test",
        generated_at=datetime(2026, 7, 23, tzinfo=timezone.utc),
    )

    assert timeline["event_count"] == 2


def test_event_timeline_embeds_every_cluster_article():
    items = [
        make_item(
            f"finance-{index}",
            f"星河动力D轮融资完成，募资数亿元 第{index}次报道",
            f"2026-07-{20 + index // 8:02d}T{index % 8:02d}:00:00Z",
            f"媒体{index}",
            "financing",
        )
        for index in range(15)
    ]

    timeline = build_event_timeline(
        items=items,
        run_id="all-articles-test",
        generated_at=datetime(2026, 7, 23, tzinfo=timezone.utc),
    )

    assert timeline["event_count"] == 1
    assert timeline["events"][0]["article_count"] == 15
    assert len(timeline["events"][0]["articles"]) == 15


def test_event_timeline_infers_missing_publication_date_from_archive():
    item = make_item(
        "undated-launch",
        "星河动力完成新一轮发射",
        "2026-07-20T08:00:00Z",
        "媒体甲",
        "launch",
    )
    item["published_at"] = None
    item["archive_first_seen_at"] = "2026-07-21T09:00:00Z"

    timeline = build_event_timeline(
        items=[item],
        run_id="inferred-date-test",
        generated_at=datetime(2026, 7, 23, tzinfo=timezone.utc),
    )

    assert timeline["article_count"] == 1
    assert timeline["inferred_date_article_count"] == 1
    assert timeline["events"][0]["articles"][0]["date_is_inferred"] is True
    assert timeline["events"][0]["latest_at"] == "2026-07-21T09:00:00Z"


def make_item(item_id, title, published_at, source_name, event_type):
    return {
        "id": item_id,
        "company_id": "galactic_energy",
        "company_name": "星河动力",
        "title": title,
        "url": f"https://example.test/{item_id}",
        "published_at": published_at,
        "source": {
            "source_id": "rss_provider",
            "source_type": "rss",
            "source_name": source_name,
            "rank_group": "media",
        },
        "quality": {
            "event_type": event_type,
            "company_relevance_score": 0.9,
            "source_quality_score": 0.7,
        },
    }
