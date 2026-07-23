"""Build a daily news-activity index and China/U.S. aerospace market snapshot."""

from __future__ import annotations

import argparse
import json
import math
import re
import shutil
import urllib.error
import urllib.request
from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from statistics import fmean
from typing import Any

import yaml


SCHEMA_VERSION = "aerospace_index_snapshot.v3"
REPORT_TIMEZONE = timezone(timedelta(hours=8), name="Asia/Shanghai")
DEFAULT_CONFIG_PATH = Path("config/market_baskets.yaml")
DEFAULT_CATALOG_PATH = Path("docs/data/news/archive/catalog.json")
DEFAULT_LOCAL_ROOT = Path("data/indices")
DEFAULT_PUBLISH_ROOT = Path("docs/data/indices")
DEFAULT_NEWS_HISTORY_DAYS = 60
DEFAULT_NEWS_BASELINE_DAYS = 30
SINA_REFERER = "https://finance.sina.com.cn/"
SINA_USER_AGENT = "Mozilla/5.0 (compatible; SDATA-A/1.0; +https://github.com/)"


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


def build_sector_snapshot(
    sector_id: str,
    sector_config: dict[str, Any],
    quotes: dict[str, dict[str, Any]],
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
    return {
        "sector_id": sector_id,
        "display_name": sector_config["display_name"],
        "currency": sector_config["currency"],
        "basket_name": f"{sector_config['display_name']}等权篮子",
        "basket_change_pct": basket_change,
        "change_pct": basket_change,
        "member_count": len(members),
        "quoted_member_count": len(valid_changes),
        "advancers": sum(1 for change in valid_changes if change > 0),
        "decliners": sum(1 for change in valid_changes if change < 0),
        "unchanged": sum(1 for change in valid_changes if change == 0),
        "members": members,
        "status": "current" if valid_changes else "unavailable",
    }


def build_index_snapshot(
    catalog: dict[str, Any],
    config: dict[str, Any],
    quotes: dict[str, dict[str, Any]],
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
        )
        for sector_id, sector_config in (config.get("sectors") or {}).items()
    }
    source = config.get("quote_source") or {}
    quoted_count = sum(
        market["quoted_member_count"] for market in markets.values()
    )
    expected_count = sum(market["member_count"] for market in markets.values())
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
            "source_id": source.get("source_id") or "sina_finance",
            "source_name": source.get("source_name") or "新浪财经行情",
            "status": "current" if quoted_count else "unavailable",
            "quoted_instruments": quoted_count,
            "expected_instruments": expected_count,
            "request_count": 1,
            "delay_notice": "行情可能存在延迟，篮子涨跌仅用于板块监测，不构成投资建议。",
        },
        "methodology": {
            "news_index": "过去 30 个自然日日均=100",
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
    previous_path = local_root / "latest" / "aerospace_index.json"
    previous = load_json(previous_path) if previous_path.exists() else None
    error_reason = None
    try:
        quotes = fetch_sina_quotes(config)
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
        quotes = {}
        error_reason = f"{type(exc).__name__}: {exc}"
    if not quotes and error_reason is None:
        error_reason = "quote source returned no valid instruments"
    payload = build_index_snapshot(catalog, config, quotes, as_of=resolved_date)
    if error_reason:
        payload = stale_market_snapshot(payload, previous, reason=error_reason)
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
