"""Build a daily news-activity index and China/U.S. aerospace market snapshot."""

from __future__ import annotations

import argparse
import json
import math
import re
import shutil
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from statistics import fmean
from typing import Any

import yaml


SCHEMA_VERSION = "aerospace_index_snapshot.v4"
REPORT_TIMEZONE = timezone(timedelta(hours=8), name="Asia/Shanghai")
DEFAULT_CONFIG_PATH = Path("config/market_baskets.yaml")
DEFAULT_CATALOG_PATH = Path("docs/data/news/archive/catalog.json")
DEFAULT_LOCAL_ROOT = Path("data/indices")
DEFAULT_PUBLISH_ROOT = Path("docs/data/indices")
DEFAULT_NEWS_HISTORY_DAYS = 60
DEFAULT_NEWS_BASELINE_DAYS = 30
SINA_REFERER = "https://finance.sina.com.cn/"
SINA_USER_AGENT = "Mozilla/5.0 (compatible; SDATA-A/1.0; +https://github.com/)"
EASTMONEY_REFERER = "https://quote.eastmoney.com/"


@dataclass(frozen=True)
class IndexOutputs:
    latest_json: Path
    published_json: Path
    archived_json: Path


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_config(path: Path) -> dict[str, Any]:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(REPORT_TIMEZONE)


def publication_date(item: dict[str, Any]) -> date | None:
    parsed = parse_datetime(item.get("published_at"))
    return parsed.date() if parsed else None


def finite_number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def news_heat_label(index_value: float | None) -> str:
    if index_value is None:
        return "基线不足"
    if index_value < 50:
        return "低热"
    if index_value < 80:
        return "偏低"
    if index_value < 120:
        return "常态"
    if index_value < 180:
        return "活跃"
    return "高热"


def build_news_activity(
    catalog: dict[str, Any],
    *,
    as_of: date,
    history_days: int = DEFAULT_NEWS_HISTORY_DAYS,
    baseline_days: int = DEFAULT_NEWS_BASELINE_DAYS,
) -> dict[str, Any]:
    counts = Counter(
        published
        for item in catalog.get("items") or []
        if (published := publication_date(item)) is not None
    )
    history: list[dict[str, Any]] = []
    first_day = as_of - timedelta(days=history_days - 1)
    for offset in range(history_days):
        current_date = first_day + timedelta(days=offset)
        baseline_counts = [
            counts[current_date - timedelta(days=days_ago)]
            for days_ago in range(1, baseline_days + 1)
        ]
        baseline_average = fmean(baseline_counts) if baseline_counts else 0
        count = counts[current_date]
        index_value = (
            round((count / baseline_average) * 100, 1) if baseline_average > 0 else None
        )
        history.append(
            {
                "date": current_date.isoformat(),
                "news_count": count,
                "baseline_average": round(baseline_average, 2),
                "index_value": index_value,
                "heat_label": news_heat_label(index_value),
            }
        )
    current = history[-1]
    return {
        "index_name": "SDATA 新闻活跃度指数",
        "as_of_date": as_of.isoformat(),
        "news_count": current["news_count"],
        "baseline_average": current["baseline_average"],
        "index_value": current["index_value"],
        "heat_label": current["heat_label"],
        "baseline_days": baseline_days,
        "base_value": 100,
        "methodology": "当日去重新闻数 ÷ 前 30 个自然日日均新闻数 × 100",
        "history": history,
    }


def parse_sina_response(payload: bytes | str) -> dict[str, dict[str, Any]]:
    text = payload.decode("gb18030", "replace") if isinstance(payload, bytes) else payload
    quotes: dict[str, dict[str, Any]] = {}
    for symbol, raw_fields in re.findall(r'var hq_str_([A-Za-z0-9_]+)="(.*?)";', text):
        fields = raw_fields.split(",") if raw_fields else []
        if not fields or not fields[0]:
            continue
        if symbol.startswith("gb_"):
            quote = parse_us_quote(symbol, fields)
        else:
            quote = parse_china_quote(symbol, fields)
        if quote:
            quotes[symbol] = quote
    return quotes


def parse_china_quote(symbol: str, fields: list[str]) -> dict[str, Any] | None:
    if len(fields) < 32:
        return None
    current = finite_number(fields[3])
    previous_close = finite_number(fields[2])
    if current is None or previous_close in (None, 0):
        return None
    change_amount = current - previous_close
    change_pct = (change_amount / previous_close) * 100
    return {
        "symbol": symbol,
        "source_name": fields[0],
        "price": round(current, 4),
        "previous_close": round(previous_close, 4),
        "open": finite_number(fields[1]),
        "high": finite_number(fields[4]),
        "low": finite_number(fields[5]),
        "change_amount": round(change_amount, 4),
        "change_pct": round(change_pct, 3),
        "volume": finite_number(fields[8]),
        "source_timestamp": f"{fields[30]} {fields[31]}".strip(),
    }


def parse_us_quote(symbol: str, fields: list[str]) -> dict[str, Any] | None:
    if len(fields) < 8:
        return None
    current = finite_number(fields[1])
    change_pct = finite_number(fields[2])
    change_amount = finite_number(fields[4])
    if current is None or change_pct is None:
        return None
    previous_close = current - change_amount if change_amount is not None else None
    return {
        "symbol": symbol,
        "source_name": fields[0],
        "price": round(current, 4),
        "previous_close": round(previous_close, 4) if previous_close is not None else None,
        "open": finite_number(fields[5]),
        "high": finite_number(fields[6]),
        "low": finite_number(fields[7]),
        "change_amount": round(change_amount, 4) if change_amount is not None else None,
        "change_pct": round(change_pct, 3),
        "volume": finite_number(fields[10]) if len(fields) > 10 else None,
        "source_timestamp": fields[3],
    }


def fetch_sina_quotes(
    config: dict[str, Any],
    *,
    timeout_seconds: int | None = None,
) -> dict[str, dict[str, Any]]:
    symbols = []
    seen_symbols: set[str] = set()
    for sector in (config.get("sectors") or {}).values():
        for member in sector.get("members") or []:
            symbol = member.get("symbol")
            if symbol and symbol not in seen_symbols:
                symbols.append(symbol)
                seen_symbols.add(symbol)
    source = config.get("quote_source") or {}
    endpoint = source.get("endpoint") or "https://hq.sinajs.cn/list="
    timeout = timeout_seconds or int(
        (source.get("request_policy") or {}).get("timeout_seconds") or 20
    )
    request = urllib.request.Request(
        f"{endpoint}{','.join(symbols)}",
        headers={"Referer": SINA_REFERER, "User-Agent": SINA_USER_AGENT},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return parse_sina_response(response.read())


def parse_eastmoney_index_response(
    payload: bytes | str,
    instrument: dict[str, Any],
) -> dict[str, Any] | None:
    text = payload.decode("utf-8", "replace") if isinstance(payload, bytes) else payload
    parsed = json.loads(text)
    if not isinstance(parsed, dict) or parsed.get("rc") not in (None, 0):
        return None
    data = parsed.get("data") if isinstance(parsed, dict) else None
    if not data:
        return None

    decimal = int(finite_number(data.get("f59")) or 2)
    percent_decimal = int(finite_number(data.get("f152")) or 2)
    values_scaled = bool(instrument.get("values_scaled"))
    price_scale = 1 if values_scaled else 10**decimal
    percent_scale = 1 if values_scaled else 10**percent_decimal
    current_raw = finite_number(data.get("f43"))
    previous_close_raw = finite_number(data.get("f60"))
    change_pct_raw = finite_number(data.get("f170"))
    if current_raw is None or previous_close_raw in (None, 0) or change_pct_raw is None:
        return None
    if data.get("f57") and instrument.get("code") and data["f57"] != instrument["code"]:
        return None

    def scaled(field: str) -> float | None:
        value = finite_number(data.get(field))
        return round(value / price_scale, decimal) if value is not None else None

    current = scaled("f43")
    previous_close = scaled("f60")
    change_pct = round(change_pct_raw / percent_scale, 3)
    if current is None or current <= 0 or previous_close is None or previous_close <= 0:
        return None
    calculated_change_pct = ((current / previous_close) - 1) * 100
    if abs(calculated_change_pct - change_pct) > 0.03:
        return None

    source_timestamp = None
    timestamp = finite_number(data.get("f86"))
    if timestamp is not None:
        source_timestamp = datetime.fromtimestamp(
            timestamp,
            REPORT_TIMEZONE,
        ).strftime("%Y-%m-%d %H:%M:%S")

    return {
        "secid": instrument["secid"],
        "symbol": data.get("f57") or instrument.get("code"),
        "ticker": instrument.get("code") or data.get("f57"),
        "name": instrument.get("name") or data.get("f58"),
        "source_name": data.get("f58") or instrument.get("name"),
        "instrument_type": "industry_index",
        "price": current,
        "previous_close": previous_close,
        "open": scaled("f46"),
        "high": scaled("f44"),
        "low": scaled("f45"),
        "change_amount": scaled("f169"),
        "change_pct": change_pct,
        "volume": finite_number(data.get("f47")),
        "turnover": finite_number(data.get("f48")),
        "source_timestamp": source_timestamp,
        "source_url": instrument.get("source_url"),
        "provider_id": instrument.get("provider_id") or "eastmoney",
        "provider_name": instrument.get("provider_name") or "东方财富",
        "status": "current",
    }


def fetch_eastmoney_indices(
    config: dict[str, Any],
    *,
    timeout_seconds: int | None = None,
) -> dict[str, dict[str, Any]]:
    source = config.get("industry_index_source") or {}
    endpoint = source.get("endpoint") or "https://push2.eastmoney.com/api/qt/stock/get"
    fields = source.get("fields") or (
        "f43,f44,f45,f46,f47,f48,f57,f58,f59,f60,f86,f152,f169,f170"
    )
    timeout = timeout_seconds or int(
        (source.get("request_policy") or {}).get("timeout_seconds") or 20
    )
    indices: dict[str, dict[str, Any]] = {}
    for sector_id, sector in (config.get("sectors") or {}).items():
        instrument = sector.get("industry_index")
        if not instrument:
            continue
        query_params = {
            "secid": instrument["secid"],
            "fields": fields,
            **(source.get("query_params") or {}),
        }
        query = urllib.parse.urlencode(query_params)
        request = urllib.request.Request(
            f"{endpoint}?{query}",
            headers={"Referer": EASTMONEY_REFERER, "User-Agent": SINA_USER_AGENT},
        )
        with urllib.request.urlopen(request, timeout=timeout) as response:
            quote = parse_eastmoney_index_response(
                response.read(),
                {
                    **instrument,
                    "values_scaled": source.get("values_scaled", False),
                },
            )
        if quote:
            indices[sector_id] = quote
    return indices


def build_sector_snapshot(
    sector_id: str,
    sector_config: dict[str, Any],
    quotes: dict[str, dict[str, Any]],
    industry_indices: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    members = []
    for configured in sector_config.get("members") or []:
        quote = quotes.get(configured["symbol"])
        if not quote:
            members.append(
                {
                    "symbol": configured["symbol"],
                    "ticker": configured["ticker"],
                    "name": configured["name"],
                    "status": "unavailable",
                }
            )
            continue
        members.append(
            {
                **quote,
                "ticker": configured["ticker"],
                "name": configured["name"],
                "source_name": quote.get("source_name") or configured["name"],
                "status": "current",
            }
        )
    valid_changes = [
        member["change_pct"]
        for member in members
        if member.get("status") == "current" and member.get("change_pct") is not None
    ]
    average_change = fmean(valid_changes) if valid_changes else None
    basket_change = round(average_change, 3) if average_change is not None else None
    configured_index = sector_config.get("industry_index")
    industry_index = (industry_indices or {}).get(sector_id)
    if configured_index and not industry_index:
        industry_index = {
            "secid": configured_index.get("secid"),
            "symbol": configured_index.get("code"),
            "ticker": configured_index.get("code"),
            "name": configured_index.get("name"),
            "instrument_type": "industry_index",
            "source_url": configured_index.get("source_url"),
            "provider_id": configured_index.get("provider_id") or "eastmoney",
            "provider_name": configured_index.get("provider_name") or "东方财富",
            "status": "unavailable",
        }
    index_is_current = bool(industry_index and industry_index.get("status") == "current")
    index_is_available = bool(
        industry_index
        and industry_index.get("status") in {"current", "stale_previous"}
        and industry_index.get("price") is not None
    )
    quoted_instrument_count = len(valid_changes) + int(index_is_current)
    expected_instrument_count = len(members) + int(bool(configured_index))
    if configured_index:
        if index_is_current and valid_changes:
            status = "current"
        elif index_is_current or valid_changes:
            status = "partial"
        else:
            status = "unavailable"
    else:
        status = "current" if valid_changes else "unavailable"
    return {
        "sector_id": sector_id,
        "display_name": sector_config["display_name"],
        "currency": sector_config["currency"],
        "basket_name": f"{sector_config['display_name']}等权篮子",
        "basket_change_pct": basket_change,
        "change_pct": basket_change,
        "industry_index": industry_index,
        "index_name": industry_index.get("name") if industry_index else None,
        "index_code": industry_index.get("ticker") if industry_index else None,
        "index_value": (
            industry_index.get("price") if index_is_available else None
        ),
        "index_change_pct": (
            industry_index.get("change_pct") if index_is_available else None
        ),
        "index_change_amount": (
            industry_index.get("change_amount") if index_is_available else None
        ),
        "index_previous_close": (
            industry_index.get("previous_close") if index_is_available else None
        ),
        "index_source_name": (
            industry_index.get("provider_name") if industry_index else None
        ),
        "index_source_timestamp": (
            industry_index.get("source_timestamp") if index_is_available else None
        ),
        "index_source_url": (
            industry_index.get("source_url") if industry_index else None
        ),
        "index_status": (
            industry_index.get("status") if industry_index else "not_configured"
        ),
        "member_count": len(members),
        "quoted_member_count": len(valid_changes),
        "quoted_instrument_count": quoted_instrument_count,
        "expected_instrument_count": expected_instrument_count,
        "advancers": sum(1 for change in valid_changes if change > 0),
        "decliners": sum(1 for change in valid_changes if change < 0),
        "unchanged": sum(1 for change in valid_changes if change == 0),
        "members": members,
        "status": status,
    }


def build_index_snapshot(
    catalog: dict[str, Any],
    config: dict[str, Any],
    quotes: dict[str, dict[str, Any]],
    industry_indices: dict[str, dict[str, Any]] | None = None,
    *,
    as_of: date,
    generated_at: datetime | None = None,
) -> dict[str, Any]:
    generated = generated_at or datetime.now(timezone.utc)
    methodology = config.get("index_methodology") or {}
    markets = {
        sector_id: build_sector_snapshot(
            sector_id,
            sector_config,
            quotes,
            industry_indices,
        )
        for sector_id, sector_config in (config.get("sectors") or {}).items()
    }
    stock_source = config.get("quote_source") or {}
    index_source = config.get("industry_index_source") or {}
    quoted_count = sum(
        market["quoted_instrument_count"] for market in markets.values()
    )
    expected_count = sum(
        market["expected_instrument_count"] for market in markets.values()
    )
    quoted_stock_count = sum(
        market["quoted_member_count"] for market in markets.values()
    )
    expected_stock_count = sum(market["member_count"] for market in markets.values())
    expected_index_count = sum(
        int(bool(sector.get("industry_index")))
        for sector in (config.get("sectors") or {}).values()
    )
    quoted_index_count = sum(
        int(bool(market.get("industry_index", {}).get("status") == "current"))
        for market in markets.values()
        if market.get("industry_index")
    )
    if quoted_count == expected_count and expected_count:
        source_status = "current"
    elif quoted_count:
        source_status = "partial"
    else:
        source_status = "unavailable"
    news_activity = build_news_activity(catalog, as_of=as_of)
    news_activity["is_partial_day"] = (
        as_of == generated.astimezone(REPORT_TIMEZONE).date()
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": generated.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
        "as_of_date": as_of.isoformat(),
        "news_activity": news_activity,
        "markets": markets,
        "market_data_source": {
            "source_id": "multi_source_market_data",
            "source_name": "新浪财经 + 东方财富",
            "status": source_status,
            "quoted_instruments": quoted_count,
            "expected_instruments": expected_count,
            "request_count": 1 + expected_index_count,
            "sources": [
                {
                    "source_id": stock_source.get("source_id") or "sina_finance",
                    "source_name": stock_source.get("source_name") or "新浪财经行情",
                    "quoted_instruments": quoted_stock_count,
                    "expected_instruments": expected_stock_count,
                },
                {
                    "source_id": index_source.get("source_id") or "eastmoney",
                    "source_name": index_source.get("source_name") or "东方财富行情",
                    "quoted_instruments": quoted_index_count,
                    "expected_instruments": expected_index_count,
                },
            ],
            "delay_notice": "中国航天航空指数来自东方财富；美国板块为等权篮子。行情可能延迟，不构成投资建议。",
        },
        "methodology": {
            "news_index": "过去 30 个自然日日均=100",
            "china_industry_index": index_source.get("methodology"),
            "sector_basket": methodology.get("basket_change_formula"),
            "weighting": methodology.get("basket_weighting") or "equal_weight",
            "sector_basket_note": methodology.get("note"),
        },
    }


def stale_market_snapshot(
    payload: dict[str, Any],
    previous: dict[str, Any] | None,
    *,
    reason: str,
) -> dict[str, Any]:
    if (
        previous
        and previous.get("schema_version") == SCHEMA_VERSION
        and previous.get("markets")
    ):
        payload["markets"] = previous["markets"]
        for market in payload["markets"].values():
            market["status"] = "stale_previous"
            for member in market.get("members") or []:
                if member.get("status") == "current":
                    member["status"] = "stale_previous"
            if market.get("industry_index"):
                market["industry_index"]["status"] = "stale_previous"
                market["index_status"] = "stale_previous"
        payload["market_data_source"].update(
            {
                "status": "stale_previous",
                "reason": reason,
                "quoted_instruments": 0,
            }
        )
    else:
        payload["market_data_source"].update({"status": "unavailable", "reason": reason})
    return payload


def reuse_previous_industry_indices(
    industry_indices: dict[str, dict[str, Any]],
    previous: dict[str, Any] | None,
    config: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    """Keep the last real index point when only the index provider is offline."""
    if not previous or previous.get("schema_version") != SCHEMA_VERSION:
        return industry_indices
    restored = dict(industry_indices)
    previous_markets = previous.get("markets") or {}
    for sector_id, sector in (config.get("sectors") or {}).items():
        if sector_id in restored or not sector.get("industry_index"):
            continue
        previous_index = (previous_markets.get(sector_id) or {}).get("industry_index")
        if (
            not previous_index
            or previous_index.get("status") not in {"current", "stale_previous"}
            or previous_index.get("price") is None
        ):
            continue
        restored[sector_id] = {**previous_index, "status": "stale_previous"}
    return restored


def load_previous_market_snapshot(local_root: Path) -> dict[str, Any] | None:
    """Find the newest snapshot that still contains a real industry-index point."""
    latest_path = local_root / "latest" / "aerospace_index.json"
    archive_paths = sorted(
        (local_root / "archive").glob("*/*/*/aerospace_index.json"),
        reverse=True,
    )
    fallback = None
    for path in [latest_path, *archive_paths]:
        if not path.exists():
            continue
        candidate = load_json(path)
        if candidate.get("schema_version") != SCHEMA_VERSION:
            continue
        if fallback is None and candidate.get("markets"):
            fallback = candidate
        if any(
            (market.get("industry_index") or {}).get("price") is not None
            for market in (candidate.get("markets") or {}).values()
        ):
            return candidate
    return fallback


def write_outputs(
    payload: dict[str, Any],
    *,
    local_root: Path,
    publish_root: Path,
    as_of: date,
) -> IndexOutputs:
    latest_json = local_root / "latest" / "aerospace_index.json"
    published_json = publish_root / "latest" / "aerospace_index.json"
    archived_json = local_root / "archive" / as_of.strftime("%Y/%m/%d") / "aerospace_index.json"
    write_json(latest_json, payload)
    published_json.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(latest_json, published_json)
    archived_json.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(latest_json, archived_json)
    return IndexOutputs(latest_json, published_json, archived_json)


def generate_index_snapshot(
    *,
    catalog_path: Path = DEFAULT_CATALOG_PATH,
    config_path: Path = DEFAULT_CONFIG_PATH,
    local_root: Path = DEFAULT_LOCAL_ROOT,
    publish_root: Path = DEFAULT_PUBLISH_ROOT,
    as_of: date | None = None,
) -> tuple[dict[str, Any], IndexOutputs]:
    catalog = load_json(catalog_path)
    config = load_config(config_path)
    resolved_date = as_of or datetime.now(REPORT_TIMEZONE).date()
    previous = load_previous_market_snapshot(local_root)
    errors: dict[str, str] = {}
    try:
        quotes = fetch_sina_quotes(config)
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
        quotes = {}
        errors["stock_quotes"] = f"{type(exc).__name__}: {exc}"
    if not quotes and "stock_quotes" not in errors:
        errors["stock_quotes"] = "quote source returned no valid instruments"
    try:
        industry_indices = fetch_eastmoney_indices(config)
    except (json.JSONDecodeError, urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
        industry_indices = {}
        errors["industry_index"] = f"{type(exc).__name__}: {exc}"
    expected_indices = sum(
        int(bool(sector.get("industry_index")))
        for sector in (config.get("sectors") or {}).values()
    )
    if expected_indices and not industry_indices and "industry_index" not in errors:
        errors["industry_index"] = "index source returned no valid instruments"
    has_current_industry_indices = bool(industry_indices)
    industry_indices = reuse_previous_industry_indices(
        industry_indices,
        previous,
        config,
    )
    payload = build_index_snapshot(
        catalog,
        config,
        quotes,
        industry_indices,
        as_of=resolved_date,
    )
    if errors:
        payload["market_data_source"]["errors"] = errors
    if not quotes and not has_current_industry_indices:
        payload = stale_market_snapshot(
            payload,
            previous,
            reason="; ".join(f"{key}: {value}" for key, value in errors.items()),
        )
    outputs = write_outputs(
        payload,
        local_root=local_root,
        publish_root=publish_root,
        as_of=resolved_date,
    )
    return payload, outputs


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG_PATH)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH)
    parser.add_argument("--local-root", type=Path, default=DEFAULT_LOCAL_ROOT)
    parser.add_argument("--publish-root", type=Path, default=DEFAULT_PUBLISH_ROOT)
    parser.add_argument("--as-of", type=date.fromisoformat)
    args = parser.parse_args(argv)

    payload, outputs = generate_index_snapshot(
        catalog_path=args.catalog,
        config_path=args.config,
        local_root=args.local_root,
        publish_root=args.publish_root,
        as_of=args.as_of,
    )
    source = payload["market_data_source"]
    print(
        f"Generated aerospace index date={payload['as_of_date']} "
        f"news_index={payload['news_activity']['index_value']} "
        f"quotes={source['quoted_instruments']}/{source['expected_instruments']} "
        f"status={source['status']} json={outputs.latest_json}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
