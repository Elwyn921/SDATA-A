import json
import urllib.parse
from datetime import date, datetime, timezone

from satellite_news.market.index_snapshot import (
    SCHEMA_VERSION,
    build_index_snapshot,
    build_news_activity,
    fetch_eastmoney_indices,
    fetch_sina_quotes,
    load_previous_market_snapshot,
    parse_eastmoney_index_response,
    parse_sina_response,
    reuse_previous_industry_indices,
    stale_market_snapshot,
)


def sample_config():
    return {
        "quote_source": {"source_id": "sina_finance", "source_name": "Sina"},
        "industry_index_source": {
            "source_id": "eastmoney",
            "source_name": "Eastmoney",
            "endpoint": "https://push2.eastmoney.com/api/qt/stock/get",
            "fields": "f43,f57,f58,f59,f60,f86,f152,f169,f170",
            "values_scaled": True,
            "query_params": {"fltt": 2, "invt": 2},
        },
        "index_methodology": {
            "basket_weighting": "equal_weight",
            "basket_change_formula": "mean return",
        },
        "sectors": {
            "china": {
                "display_name": "中国航空航天板块",
                "currency": "CNY",
                "industry_index": {
                    "secid": "90.BK0480",
                    "code": "BK0480",
                    "name": "航天航空指数",
                    "provider_name": "东方财富",
                    "source_url": "https://quote.eastmoney.com/bk/90.BK0480.html",
                },
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
        f'var hq_str_sz000768="{",".join([china_fields[0], china_fields[1], china_fields[2], "0", *china_fields[4:]])}";\n'
        f'var hq_str_gb_ba="{",".join(us_fields)}";'
    )

    quotes = parse_sina_response(payload)

    assert quotes["sh600118"]["price"] == 60.12
    assert quotes["sh600118"]["change_pct"] == 0.856
    assert "sz000768" not in quotes
    assert quotes["gb_ba"]["price"] == 208.65
    assert quotes["gb_ba"]["change_pct"] == 1.88


def test_parse_eastmoney_index_response_handles_display_and_raw_values():
    display_payload = json.dumps(
        {
            "rc": 0,
            "data": {
                "f43": 47303.73,
                "f44": 47498.13,
                "f45": 46693.39,
                "f46": 46700.79,
                "f47": 4268596,
                "f48": 10636724999.0,
                "f57": "BK0480",
                "f58": "航天航空",
                "f59": 2,
                "f60": 46717.05,
                "f86": 1784783112,
                "f152": 2,
                "f169": 586.68,
                "f170": 1.26,
            },
        },
        ensure_ascii=False,
    )
    instrument = {
        "secid": "90.BK0480",
        "code": "BK0480",
        "name": "航天航空指数",
        "provider_name": "东方财富",
        "values_scaled": True,
    }

    quote = parse_eastmoney_index_response(display_payload, instrument)

    assert quote["price"] == 47303.73
    assert quote["previous_close"] == 46717.05
    assert quote["change_amount"] == 586.68
    assert quote["change_pct"] == 1.26
    assert quote["source_timestamp"] == "2026-07-23 13:05:12"

    raw_payload = display_payload.replace("47303.73", "4730373")
    raw_payload = raw_payload.replace("47498.13", "4749813")
    raw_payload = raw_payload.replace("46693.39", "4669339")
    raw_payload = raw_payload.replace("46700.79", "4670079")
    raw_payload = raw_payload.replace("46717.05", "4671705")
    raw_payload = raw_payload.replace("586.68", "58668")
    raw_payload = raw_payload.replace("1.26", "126")
    raw_quote = parse_eastmoney_index_response(
        raw_payload,
        {key: value for key, value in instrument.items() if key != "values_scaled"},
    )
    assert raw_quote["price"] == 47303.73
    assert raw_quote["change_pct"] == 1.26

    mismatched = parse_eastmoney_index_response(
        display_payload,
        {**instrument, "code": "WRONG"},
    )
    assert mismatched is None


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


def test_fetch_eastmoney_indices_requests_the_configured_board_once(monkeypatch):
    captured = []
    payload = json.dumps(
        {
            "rc": 0,
            "data": {
                "f43": 47303.73,
                "f57": "BK0480",
                "f58": "航天航空",
                "f59": 2,
                "f60": 46717.05,
                "f86": 1784783112,
                "f152": 2,
                "f169": 586.68,
                "f170": 1.26,
            },
        },
        ensure_ascii=False,
    ).encode()

    class EastmoneyResponse:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def read(self):
            return payload

    def fake_urlopen(request, timeout):
        captured.append((request, timeout))
        return EastmoneyResponse()

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    indices = fetch_eastmoney_indices(sample_config())

    assert indices["china"]["price"] == 47303.73
    assert len(captured) == 1
    query = urllib.parse.parse_qs(urllib.parse.urlsplit(captured[0][0].full_url).query)
    assert query["secid"] == ["90.BK0480"]
    assert query["fltt"] == ["2"]
    assert captured[0][0].get_header("Referer") == "https://quote.eastmoney.com/"


def test_news_activity_uses_previous_30_calendar_day_average():
    activity = build_news_activity(sample_catalog(), as_of=date(2026, 7, 23))

    assert activity["news_count"] == 5
    assert activity["baseline_average"] == 0.67
    assert activity["index_value"] == 750.0
    assert activity["heat_label"] == "高热"
    assert len(activity["history"]) == 60


def test_index_snapshot_adds_eastmoney_china_index_and_keeps_us_basket():
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

    industry_indices = {
        "china": {
            "secid": "90.BK0480",
            "symbol": "BK0480",
            "ticker": "BK0480",
            "name": "航天航空指数",
            "source_name": "航天航空",
            "instrument_type": "industry_index",
            "price": 47303.73,
            "previous_close": 46717.05,
            "change_amount": 586.68,
            "change_pct": 1.26,
            "source_timestamp": "2026-07-23 13:05:12",
            "source_url": "https://quote.eastmoney.com/bk/90.BK0480.html",
            "provider_id": "eastmoney",
            "provider_name": "东方财富",
            "status": "current",
        }
    }
    payload = build_index_snapshot(
        sample_catalog(),
        sample_config(),
        quotes,
        industry_indices,
        as_of=date(2026, 7, 23),
        generated_at=datetime(2026, 7, 23, tzinfo=timezone.utc),
    )

    china = payload["markets"]["china"]
    united_states = payload["markets"]["united_states"]
    assert payload["schema_version"] == SCHEMA_VERSION
    assert china["basket_name"] == "中国航空航天板块等权篮子"
    assert china["basket_change_pct"] == 0
    assert china["change_pct"] == 0
    assert china["index_name"] == "航天航空指数"
    assert china["index_code"] == "BK0480"
    assert china["index_value"] == 47303.73
    assert china["index_change_pct"] == 1.26
    assert china["index_source_name"] == "东方财富"
    assert china["index_status"] == "current"
    assert china["advancers"] == 1
    assert china["decliners"] == 1
    assert "index_base" not in china
    assert united_states["change_pct"] == 2
    assert united_states["basket_change_pct"] == 2
    assert united_states["index_status"] == "not_configured"
    assert payload["market_data_source"]["status"] == "current"
    assert payload["market_data_source"]["quoted_instruments"] == 4
    assert payload["market_data_source"]["expected_instruments"] == 4
    assert payload["market_data_source"]["request_count"] == 2


def test_missing_eastmoney_index_does_not_hide_current_basket_quotes():
    quotes = {
        "sh600118": {
            "symbol": "sh600118",
            "source_name": "中国卫星",
            "price": 10.1,
            "previous_close": 10,
            "change_amount": 0.1,
            "change_pct": 1.0,
            "source_timestamp": "2026-07-23 15:00:00",
        }
    }
    payload = build_index_snapshot(
        sample_catalog(),
        sample_config(),
        quotes,
        {},
        as_of=date(2026, 7, 23),
        generated_at=datetime(2026, 7, 23, tzinfo=timezone.utc),
    )

    china = payload["markets"]["china"]
    assert china["basket_change_pct"] == 1
    assert china["index_value"] is None
    assert china["index_status"] == "unavailable"
    assert china["status"] == "partial"
    assert payload["market_data_source"]["status"] == "partial"


def test_missing_eastmoney_index_reuses_previous_real_point():
    previous = build_index_snapshot(
        sample_catalog(),
        sample_config(),
        {},
        {
            "china": {
                "ticker": "BK0480",
                "name": "航天航空指数",
                "price": 47303.73,
                "previous_close": 46717.05,
                "change_amount": 586.68,
                "change_pct": 1.26,
                "source_timestamp": "2026-07-23 13:05:12",
                "provider_name": "东方财富",
                "status": "current",
            }
        },
        as_of=date(2026, 7, 23),
        generated_at=datetime(2026, 7, 23, tzinfo=timezone.utc),
    )
    restored = reuse_previous_industry_indices({}, previous, sample_config())
    payload = build_index_snapshot(
        sample_catalog(),
        sample_config(),
        {},
        restored,
        as_of=date(2026, 7, 24),
        generated_at=datetime(2026, 7, 24, tzinfo=timezone.utc),
    )

    assert payload["markets"]["china"]["index_value"] == 47303.73
    assert payload["markets"]["china"]["index_change_pct"] == 1.26
    assert payload["markets"]["china"]["index_status"] == "stale_previous"
    assert payload["market_data_source"]["quoted_instruments"] == 0


def test_previous_market_snapshot_prefers_archived_real_index(tmp_path):
    latest = tmp_path / "latest" / "aerospace_index.json"
    archived = tmp_path / "archive" / "2026" / "07" / "23" / "aerospace_index.json"
    latest.parent.mkdir(parents=True)
    archived.parent.mkdir(parents=True)
    latest.write_text(
        json.dumps(
            {
                "schema_version": SCHEMA_VERSION,
                "markets": {"china": {"industry_index": {"status": "unavailable"}}},
            }
        ),
        encoding="utf-8",
    )
    archived.write_text(
        json.dumps(
            {
                "schema_version": SCHEMA_VERSION,
                "markets": {
                    "china": {
                        "industry_index": {
                            "status": "current",
                            "price": 48105.81,
                        }
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    previous = load_previous_market_snapshot(tmp_path)

    assert previous["markets"]["china"]["industry_index"]["price"] == 48105.81


def test_stale_snapshot_does_not_reuse_old_synthetic_point_schema():
    payload = build_index_snapshot(
        sample_catalog(),
        sample_config(),
        {},
        as_of=date(2026, 7, 23),
        generated_at=datetime(2026, 7, 23, tzinfo=timezone.utc),
    )

    previous_v3 = {
        "schema_version": "aerospace_index_snapshot.v3",
        "markets": {"china": {"index_value": 1000}},
    }
    stale = stale_market_snapshot(payload, previous_v3, reason="offline")
    assert stale["markets"]["china"]["index_value"] is None
    assert stale["markets"]["china"]["basket_change_pct"] is None
    assert stale["market_data_source"]["status"] == "unavailable"

    previous_v4 = {
        "schema_version": SCHEMA_VERSION,
        "markets": {
            "china": {
                "status": "current",
                "index_status": "current",
                "industry_index": {"status": "current", "price": 47303.73},
                "members": [{"status": "current", "ticker": "600118.SH"}],
            }
        },
    }
    stale_current_schema = stale_market_snapshot(payload, previous_v4, reason="offline")
    assert stale_current_schema["markets"]["china"]["status"] == "stale_previous"
    assert stale_current_schema["markets"]["china"]["index_status"] == "stale_previous"
    assert (
        stale_current_schema["markets"]["china"]["industry_index"]["status"]
        == "stale_previous"
    )
