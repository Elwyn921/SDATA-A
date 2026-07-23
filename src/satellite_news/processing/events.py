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
            "回收验证",
            "静态点火",
            "热试车",
            "发动机试车",
            "总装测试",
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
            "战略投资",
            "增资扩股",
            "完成交割",
            "投资人",
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
            "框架合同",
            "发射服务合同",
            "入围",
            "招标",
            "集采",
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
            "批复",
            "牌照发放",
            "管理办法",
            "征求意见",
            "监管规则",
            "环评公示",
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
            "上市辅导",
            "问询回复",
            "上交所",
            "深交所",
            "证监会",
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
            "战略合作",
            "联合研发",
            "达成合作",
            "携手",
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
            "研制",
            "研发",
            "总装",
            "产能",
            "生产基地",
            "产业基地",
            "新型号",
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
            "高管",
            "创始人",
            "管理层",
            "总部",
            "迁址",
            "工商变更",
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
    "valuation",
    "ipo",
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
    "上市",
    "招股书",
    "上市辅导",
    "上交所",
    "深交所",
    "证监会",
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
    earliest_at = min((row["published_at"] for row in rows), default=None)
    latest_at = max((row["published_at"] for row in rows), default=None)
    return {
        "schema_version": "company_event_timeline.v2",
        "artifact_version": 1,
        "run_id": run_id,
        "generated_at": isoformat(generated_at),
        "event_count": len(events),
        "article_count": len(rows),
        "embedded_article_count": sum(len(event["articles"]) for event in events),
        "inferred_date_article_count": sum(
            1 for row in rows if row["date_is_inferred"]
        ),
        "company_count": len(company_ids),
        "earliest_at": isoformat(earliest_at) if earliest_at else None,
        "latest_at": isoformat(latest_at) if latest_at else None,
        "is_complete": True,
        "event_type_counts": dict(sorted(type_counts.items())),
        "events": events,
    }


def event_article(item: dict[str, Any]) -> dict[str, Any]:
    source = item.get("source") if isinstance(item.get("source"), dict) else {}
    quality = item.get("quality") if isinstance(item.get("quality"), dict) else {}
    metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
    title = str(item.get("title") or "Untitled event")
    stored_event_type = str(
        quality.get("event_type")
        or metadata.get("event_type")
        or "other"
    )
    title_event_type = classify_event_type(title)
    event_type = title_event_type if title_event_type != "other" else stored_event_type
    published_at = parse_datetime(item.get("published_at"))
    date_is_inferred = published_at is None
    published_at = published_at or parse_datetime(item.get("archive_first_seen_at"))
    return {
        "id": str(item.get("id") or item.get("url") or item.get("title") or "unknown"),
        "company_id": str(item.get("company_id") or "unknown"),
        "company_name": str(item.get("company_name") or item.get("company_id") or "unknown"),
        "title": title,
        "url": str(item.get("url") or ""),
        "published_at": published_at,
        "date_is_inferred": date_is_inferred,
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
        if any(
            same_event(
                row["title"],
                article["title"],
                company_name=str(row["company_name"]),
            )
            for article in cluster["articles"]
        ):
            return cluster
    return None


def same_event(left: str, right: str, *, company_name: str = "") -> bool:
    left_normalized = event_title_core(left, company_name=company_name)
    right_normalized = event_title_core(right, company_name=company_name)
    if SequenceMatcher(None, left_normalized, right_normalized).ratio() >= 0.52:
        return True
    left_terms = title_terms(left_normalized)
    right_terms = title_terms(right_normalized)
    if not left_terms or not right_terms:
        return False
    overlap = len(left_terms & right_terms)
    return overlap >= 2 and overlap / min(len(left_terms), len(right_terms)) >= 0.4


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
                "date_is_inferred": article["date_is_inferred"],
                "source_name": article["source_name"],
            }
            for article in sorted(
                articles,
                key=lambda row: row["published_at"],
                reverse=True,
            )
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


def event_title_core(value: str, *, company_name: str) -> str:
    text = normalized_title(value)
    company = normalized_title(company_name)
    if company:
        text = text.replace(company, " ")
    return " ".join(text.split())


def title_terms(value: str) -> set[str]:
    words = {word for word in value.split() if len(word) >= 3}
    chinese = "".join(re.findall(r"[\u4e00-\u9fff]", value))
    bigrams = {chinese[index : index + 2] for index in range(max(0, len(chinese) - 1))}
    stop = {
        "公司",
        "航天",
        "卫星",
        "火箭",
        "商业",
        "中国",
        "成功",
        "完成",
        "正式",
        "最新",
        "消息",
        "宣布",
        "项目",
        "企业",
    }
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
