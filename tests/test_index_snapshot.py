from datetime import date, datetime, timezone

from satellite_news.market.index_snapshot import (
    SCHEMA_VERSION,
    build_index_snapshot,
    build_news_activity,
    fetch_sina_quotes,
    parse_sina_response,
    stale_market_snapshot,
)


def sample_config():
    return {
        "quote_source": {"source_id": "sina_finance", "source_name": "Sina"},
        "index_methodology": {
            "basket_weighting": "equal_weight",
            "basket_change_formula": "mean return",
        },
        "sectors": {
            "china": {
                "display_name": "中国航空航天板块",
                "currency": "CNY",
                "members": [
                    {"symbol": "sh600118", "ticker": "600118.SH", "name": "中国卫星"},
                    {"symbol": "sz000768", "ticker": "000768.SZ", "name": "中航西飞"},
                ],
            },
            "united_states": {
                "display_name": "美国航空航天板块",
                "currency": "USD",
                "members": [{"symbol": "gb_ba", "ticker": "BA", "name": "Boeing"}],
            },
        },
    }


def sample_catalog():
    items = []
    for day_offset, count in enumerate([2, 4, 6, 8], start=1):
        for item_index in range(count):
            items.append(
                {
                    "id": f"{day_offset}-{item_index}",
                    "published_at": f"2026-07-{23 - day_offset:02d}T04:00:00Z",
                }
            )
    items.extend(
        {"id": f"today-{index}", "published_at": "2026-07-23T04:00:00Z"}
        for index in range(5)
    )
    return {"generated_at": "2026-07-23T05:00:00Z", "items": items}


def test_parse_sina_response_handles_china_and_us_formats():
    china_fields = [
        "中国卫星",
        "58.690",
        "59.610",
        "60.120",
        "61.690",
        "58.690",
        "60.120",
        "60.130",
        "27763665",
        "1682047085",
    ] + ["0"] * 20 + ["2026-07-23", "11:30:00"]
    us_fields = [
        "波音",
        "208.6500",
        "1.88",
        "2026-07-23 09:40:44",
        "3.8500",
        "205.0000",
        "209.2500",
        "204.8800",
        "0",
        "0",
        "6061392",
    ]
    payload = (
        f'var hq_str_sh600118="{",".join(china_fields)}";\n'
        f'var hq_str_gb_ba="{",".join(us_fields)}";'
    )

    quotes = parse_sina_response(payload)

    assert quotes["sh600118"]["price"] == 60.12
    assert quotes["sh600118"]["change_pct"] == 0.856
    assert quotes["gb_ba"]["price"] == 208.65
    assert quotes["gb_ba"]["change_pct"] == 1.88


def test_fetch_sina_quotes_batches_members_once(monkeypatch):
    captured = []

    class EmptyResponse:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def read(self):
            return b""

    def fake_urlopen(request, timeout):
        captured.append((request.full_url, timeout))
        return EmptyResponse()

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    assert fetch_sina_quotes(sample_config()) == {}
    assert len(captured) == 1
    requested_symbols = captured[0][0].split("list=", 1)[1].split(",")
    assert requested_symbols == [
        "sh600118",
        "sz000768",
        "gb_ba",
    ]


def test_news_activity_uses_previous_30_calendar_day_average():
    activity = build_news_activity(sample_catalog(), as_of=date(2026, 7, 23))

    assert activity["news_count"] == 5
    assert activity["baseline_average"] == 0.67
    assert activity["index_value"] == 750.0
    assert activity["heat_label"] == "高热"
    assert len(activity["history"]) == 60


def test_index_snapshot_reports_only_equal_weight_basket_changes():
    quotes = {
        "sh600118": {
            "symbol": "sh600118",
            "source_name": "中国卫星",
            "price": 10.1,
            "previous_close": 10,
            "change_amount": 0.1,
            "change_pct": 1.0,
            "source_timestamp": "2026-07-23 15:00:00",
        },
        "sz000768": {
            "symbol": "sz000768",
            "source_name": "中航西飞",
            "price": 19.8,
            "previous_close": 20,
            "change_amount": -0.2,
            "change_pct": -1.0,
            "source_timestamp": "2026-07-23 15:00:00",
        },
        "gb_ba": {
            "symbol": "gb_ba",
            "source_name": "波音",
            "price": 204,
            "previous_close": 200,
            "change_amount": 4,
            "change_pct": 2.0,
            "source_timestamp": "2026-07-23 10:00:00",
        },
    }

    payload = build_index_snapshot(
        sample_catalog(),
        sample_config(),
        quotes,
        as_of=date(2026, 7, 23),
        generated_at=datetime(2026, 7, 23, tzinfo=timezone.utc),
    )

    china = payload["markets"]["china"]
    united_states = payload["markets"]["united_states"]
    assert payload["schema_version"] == SCHEMA_VERSION
    assert china["basket_name"] == "中国航空航天板块等权篮子"
    assert china["basket_change_pct"] == 0
    assert china["change_pct"] == 0
    assert china["advancers"] == 1
    assert china["decliners"] == 1
    assert "index_base" not in china
    assert "index_value" not in china
    assert "benchmark" not in china
    assert united_states["change_pct"] == 2
    assert united_states["basket_change_pct"] == 2
    assert payload["market_data_source"]["quoted_instruments"] == 3
    assert payload["market_data_source"]["expected_instruments"] == 3


def test_stale_snapshot_does_not_reuse_old_synthetic_point_schema():
    payload = build_index_snapshot(
        sample_catalog(),
        sample_config(),
        {},
        as_of=date(2026, 7, 23),
        generated_at=datetime(2026, 7, 23, tzinfo=timezone.utc),
    )

    previous_v2 = {
        "schema_version": "aerospace_index_snapshot.v2",
        "markets": {"china": {"index_value": 1000}},
    }
    stale = stale_market_snapshot(payload, previous_v2, reason="offline")
    assert "index_value" not in stale["markets"]["china"]
    assert stale["markets"]["china"]["basket_change_pct"] is None
    assert stale["market_data_source"]["status"] == "unavailable"
