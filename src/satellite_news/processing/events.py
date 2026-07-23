"""Deterministic company-event classification and timeline clustering."""

from __future__ import annotations

import hashlib
import re
import unicodedata
from collections import Counter
from datetime import datetime, timedelta, timezone
from difflib import SequenceMatcher
from typing import Any


EVENT_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "launch",
        (
            "launch",
            "liftoff",
            "orbit",
            "mission",
            "发射",
            "首飞",
            "入轨",
            "一箭",
            "运载火箭",
            "试飞",
            "回收试验",
        ),
    ),
    (
        "financing",
        (
            "funding",
            "financing",
            "fundraise",
            "investment round",
            "融资",
            "增资",
            "募资",
            "投资方",
            "估值",
            "pre-a",
            "pre-b",
            "a轮",
            "b轮",
            "c轮",
            "d轮",
        ),
    ),
    (
        "order",
        (
            "contract",
            "order",
            "award",
            "procurement",
            "selected to",
            "合同",
            "订单",
            "中标",
            "采购",
            "签约",
            "交付",
        ),
    ),
    (
        "regulation",
        (
            "regulatory",
            "regulator",
            "license",
            "approval",
            "fcc",
            "监管",
            "牌照",
            "许可",
            "审批",
            "备案",
            "政策",
        ),
    ),
    (
        "market",
        (
            "share price",
            "stock price",
            "market cap",
            "valuation",
            "ipo",
            "shares",
            "股价",
            "股票",
            "涨停",
            "跌停",
            "大涨",
            "大跌",
            "概念股",
            "市值",
            "科创板",
            "创业板",
            "上市",
            "招股书",
            "ipo",
            "a股",
            "港股",
        ),
    ),
    (
        "partnership",
        (
            "partnership",
            "partner with",
            "memorandum",
            "joint venture",
            "合作",
            "战略协议",
            "合作意向",
            "合资",
            "签署协议",
        ),
    ),
    (
        "product",
        (
            "unveil",
            "debut",
            "new product",
            "factory",
            "production",
            "下线",
            "发布",
            "亮相",
            "投产",
            "工厂",
            "生产线",
            "发动机试车",
        ),
    ),
    (
        "corporate",
        (
            "appoint",
            "executive",
            "chief executive",
            "acquisition",
            "recruitment",
            "任命",
            "董事",
            "总经理",
            "董事长",
            "招聘",
            "收购",
            "股东",
            "持股",
        ),
    ),
)

EVENT_LABELS = {
    "launch": "发射与试验",
    "financing": "融资",
    "order": "订单与合同",
    "regulation": "监管与政策",
    "market": "股价与资本市场",
    "partnership": "合作",
    "product": "产品与产能",
    "corporate": "公司治理",
    "other": "其他动态",
}

EVENT_WINDOWS = {
    "launch": 2,
    "financing": 7,
    "order": 7,
    "regulation": 7,
    "market": 2,
    "partnership": 7,
    "product": 5,
    "corporate": 7,
    "other": 2,
}
MARKET_PRIORITY_TERMS = (
    "share price",
    "stock price",
    "market cap",
    "shares rose",
    "shares fell",
    "股价",
    "股票",
    "涨停",
    "跌停",
    "大涨",
    "大跌",
    "概念股",
    "市值",
    "a股",
    "港股",
    "科创板",
    "创业板",
)


def classify_event_type(text: str) -> str:
    normalized = normalize_event_text(text)
    if any(term_match(term, normalized) for term in MARKET_PRIORITY_TERMS):
        return "market"
    for event_type, terms in EVENT_RULES:
        if any(term_match(term, normalized) for term in terms):
            return event_type
    return "other"


def build_event_timeline(
    *,
    items: list[dict[str, Any]],
    run_id: str,
    generated_at: datetime,
) -> dict[str, Any]:
    rows = [event_article(item) for item in items if isinstance(item, dict)]
    rows = [row for row in rows if row["published_at"] is not None]
    rows.sort(key=lambda row: row["published_at"])

    clusters: list[dict[str, Any]] = []
    for row in rows:
        cluster = find_cluster(row=row, clusters=clusters)
        if cluster is None:
            clusters.append(
                {
                    "company_id": row["company_id"],
                    "company_name": row["company_name"],
                    "event_type": row["event_type"],
                    "articles": [row],
                    "started_at": row["published_at"],
                    "latest_at": row["published_at"],
                }
            )
        else:
            cluster["articles"].append(row)
            cluster["started_at"] = min(cluster["started_at"], row["published_at"])
            cluster["latest_at"] = max(cluster["latest_at"], row["published_at"])

    events = [finalize_cluster(cluster) for cluster in clusters]
    events.sort(
        key=lambda event: (
            str(event.get("latest_at") or ""),
            int(event.get("importance_score") or 0),
        ),
        reverse=True,
    )
    type_counts = Counter(str(event["event_type"]) for event in events)
    company_ids = {str(event["company_id"]) for event in events}
    return {
        "schema_version": "company_event_timeline.v1",
        "artifact_version": 1,
        "run_id": run_id,
        "generated_at": isoformat(generated_at),
        "event_count": len(events),
        "company_count": len(company_ids),
        "event_type_counts": dict(sorted(type_counts.items())),
        "events": events,
    }


def event_article(item: dict[str, Any]) -> dict[str, Any]:
    source = item.get("source") if isinstance(item.get("source"), dict) else {}
    quality = item.get("quality") if isinstance(item.get("quality"), dict) else {}
    metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
    event_type = str(
        quality.get("event_type")
        or metadata.get("event_type")
        or classify_event_type(str(item.get("title") or ""))
    )
    return {
        "id": str(item.get("id") or item.get("url") or item.get("title") or "unknown"),
        "company_id": str(item.get("company_id") or "unknown"),
        "company_name": str(item.get("company_name") or item.get("company_id") or "unknown"),
        "title": str(item.get("title") or "Untitled event"),
        "url": str(item.get("url") or ""),
        "published_at": parse_datetime(item.get("published_at")),
        "source_name": str(source.get("source_name") or source.get("source_id") or "未知来源"),
        "event_type": event_type if event_type in EVENT_LABELS else "other",
        "source_quality_score": float(
            quality.get("source_quality_score")
            or metadata.get("source_quality_score")
            or 0
        ),
        "relevance_score": float(
            quality.get("company_relevance_score")
            or metadata.get("company_relevance_score")
            or 0
        ),
    }


def find_cluster(*, row: dict[str, Any], clusters: list[dict[str, Any]]):
    max_age = timedelta(days=EVENT_WINDOWS.get(str(row["event_type"]), 2))
    for cluster in reversed(clusters):
        if cluster["company_id"] != row["company_id"]:
            continue
        if cluster["event_type"] != row["event_type"]:
            continue
        if row["published_at"] - cluster["latest_at"] > max_age:
            continue
        if any(same_event(row["title"], article["title"]) for article in cluster["articles"]):
            return cluster
        if row["event_type"] != "other" and row["published_at"].date() == cluster["latest_at"].date():
            return cluster
    return None


def same_event(left: str, right: str) -> bool:
    left_normalized = normalized_title(left)
    right_normalized = normalized_title(right)
    if SequenceMatcher(None, left_normalized, right_normalized).ratio() >= 0.46:
        return True
    left_terms = title_terms(left_normalized)
    right_terms = title_terms(right_normalized)
    if not left_terms or not right_terms:
        return False
    overlap = len(left_terms & right_terms)
    return overlap >= 2 and overlap / min(len(left_terms), len(right_terms)) >= 0.34


def finalize_cluster(cluster: dict[str, Any]) -> dict[str, Any]:
    articles = sorted(
        cluster["articles"],
        key=lambda row: (
            row["source_quality_score"],
            row["relevance_score"],
            row["published_at"],
        ),
        reverse=True,
    )
    representative = articles[0]
    sources = sorted({str(article["source_name"]) for article in articles})
    event_type = str(cluster["event_type"])
    identity = "|".join(
        (
            str(cluster["company_id"]),
            event_type,
            cluster["started_at"].date().isoformat(),
            normalized_title(representative["title"]),
        )
    )
    event_id = hashlib.sha1(identity.encode("utf-8")).hexdigest()[:16]
    article_count = len(articles)
    source_count = len(sources)
    importance = min(
        100,
        35
        + article_count * 8
        + source_count * 4
        + (12 if event_type in {"launch", "financing", "order", "regulation"} else 0),
    )
    return {
        "event_id": event_id,
        "company_id": cluster["company_id"],
        "company_name": cluster["company_name"],
        "event_type": event_type,
        "event_label": EVENT_LABELS[event_type],
        "headline": representative["title"],
        "summary": (
            f"{cluster['company_name']}的{EVENT_LABELS[event_type]}事件，"
            f"已汇集 {article_count} 篇报道、{source_count} 个来源。"
        ),
        "started_at": isoformat(cluster["started_at"]),
        "latest_at": isoformat(cluster["latest_at"]),
        "article_count": article_count,
        "source_count": source_count,
        "source_names": sources,
        "importance_score": importance,
        "latest_url": representative["url"],
        "articles": [
            {
                "id": article["id"],
                "title": article["title"],
                "url": article["url"],
                "published_at": isoformat(article["published_at"]),
                "source_name": article["source_name"],
            }
            for article in sorted(
                articles,
                key=lambda row: row["published_at"],
                reverse=True,
            )[:12]
        ],
    }


def normalize_event_text(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", str(value)).casefold().split())


def term_match(term: str, text: str) -> bool:
    normalized = normalize_event_text(term)
    if re.search(r"[\u4e00-\u9fff]", normalized):
        return normalized in text
    return re.search(rf"(?<![a-z0-9]){re.escape(normalized)}[a-z]*(?![a-z0-9])", text) is not None


def normalized_title(value: str) -> str:
    text = normalize_event_text(value)
    text = re.sub(r"\s+[-|–—]\s+[^-|–—]{2,40}$", "", text)
    return re.sub(r"[^\w\u4e00-\u9fff]+", " ", text).strip()


def title_terms(value: str) -> set[str]:
    words = {word for word in value.split() if len(word) >= 3}
    chinese = "".join(re.findall(r"[\u4e00-\u9fff]", value))
    bigrams = {chinese[index : index + 2] for index in range(max(0, len(chinese) - 1))}
    stop = {"公司", "航天", "卫星", "火箭", "商业", "中国", "成功", "完成", "正式"}
    return (words | bigrams) - stop


def parse_datetime(value: object) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def isoformat(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
