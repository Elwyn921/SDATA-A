"""Deterministic relevance, recency, canonicalization, and de-duplication gate."""

from __future__ import annotations

import hashlib
import re
import unicodedata
import urllib.parse
from dataclasses import replace
from datetime import timezone
from difflib import SequenceMatcher

from satellite_news.processing.events import classify_event_type
from satellite_news.schema import Company, NewsItem, PipelineContext


GENERIC_TERMS = {
    "space",
    "satellite",
    "launch",
    "rocket",
    "china",
    "technology",
    "internet",
    "航天",
    "卫星",
    "火箭",
    "发射",
    "commercial satellite",
    "small satellite",
    "satellite manufacturing",
    "商业卫星",
    "小卫星",
    "卫星制造",
    "卫星互联网",
    "商业航天",
}
INDUSTRY_TERMS = (
    "satellite",
    "constellation",
    "launch",
    "rocket",
    "spacecraft",
    "orbital",
    "broadband",
    "direct to cell",
    "leo",
    "funding",
    "financing",
    "investment",
    "contract",
    "partnership",
    "acquisition",
    "ipo",
    "license",
    "regulatory",
    "卫星",
    "星座",
    "火箭",
    "发射",
    "航天",
    "互联网",
    "入轨",
    "融资",
    "投资",
    "合同",
    "合作",
    "收购",
    "上市",
    "牌照",
    "监管",
    "增资",
    "董事",
    "总经理",
)
MARKET_TERMS = (
    "share price",
    "stock price",
    "shares",
    "market cap",
    "valuation",
    "public listing",
    "ipo",
    "股价",
    "股票",
    "涨停",
    "跌停",
    "上涨",
    "下跌",
    "大涨",
    "大跌",
    "概念股",
    "产业链",
    "市值",
    "估值",
    "a股",
    "港股",
    "科创板",
    "创业板",
    "上市",
    "招股书",
    "辅导备案",
    "证券",
    "定增",
    "并购",
    "持股",
    "参股",
    "股东",
    "资本市场",
)
RANK_SCORES = {
    "official": 1.0,
    "regulator_and_filing": 0.98,
    "wire_and_aggregator": 0.8,
    "wire": 0.8,
    "media": 0.7,
    "search": 0.55,
}
MAX_AGE_DAYS = 45
LOW_INFORMATION_TITLE_MARKERS = (
    "联系我们",
    "法律声明",
    "关于我们",
    "画廊",
    "关注我们",
    "企业新闻:",
)


class QualityNewsProcessor:
    """Apply the configured quality policy before items reach latest/archive outputs."""

    def __init__(
        self,
        *,
        companies: tuple[Company, ...],
        max_age_days: int | None = MAX_AGE_DAYS,
    ) -> None:
        self.companies = {company.id: company for company in companies}
        self.max_age_days = max_age_days

    def process(
        self,
        *,
        items: tuple[NewsItem, ...],
        context: PipelineContext,
    ) -> tuple[NewsItem, ...]:
        accepted: list[NewsItem] = []
        rejected: list[dict[str, object]] = []
        decision_counts = {"published": 0, "watchlist": 0, "rejected": 0}

        for item in items:
            assessed, decision, reasons = self.assess(item=item, context=context)
            decision_counts[decision] += 1
            if decision == "published":
                accepted.append(assessed)
            else:
                rejected.append(
                    {
                        "item_id": item.id,
                        "company_id": item.company_id,
                        "title": item.title,
                        "decision": decision,
                        "reason_codes": reasons,
                    }
                )

        deduplicated, duplicate_count = deduplicate_items(accepted)
        context.metadata["quality_gate"] = {
            "schema_version": "news_quality_gate.v1",
            "input_count": len(items),
            "published_count": len(deduplicated),
            "watchlist_count": decision_counts["watchlist"],
            "rejected_count": decision_counts["rejected"],
            "duplicate_count": duplicate_count,
            "china_relaxed_published_count": sum(
                1
                for item in deduplicated
                if any(
                    reason.startswith("china_")
                    for reason in item.metadata.get("quality_reason_codes", ())
                )
            ),
            "rejected_samples": rejected[:50],
        }
        return tuple(deduplicated)

    def assess(
        self,
        *,
        item: NewsItem,
        context: PipelineContext,
    ) -> tuple[NewsItem, str, list[str]]:
        company = self.companies.get(item.company_id)
        canonical_url = canonicalize_url(item.url)
        title_text = normalize_text(item.title)
        body_text = normalize_text(item.normalized_text or item.raw_text or "")
        text = f"{title_text} {body_text}".strip()
        reasons: list[str] = []
        company_terms = strong_company_terms(company)
        company_matches = [term for term in company_terms if term_matches(term, title_text)]
        program_matches = [
            term for term in strong_program_terms(company) if term_matches(term, title_text)
        ]
        body_company_matches = [
            term for term in company_terms if term_matches(term, body_text) and term not in company_matches
        ]
        industry_matches = [term for term in INDUSTRY_TERMS if context_term_matches(term, text)]
        market_matches = [term for term in MARKET_TERMS if context_term_matches(term, text)]
        excluded_matches = [
            term for term in (company.keywords_exclude if company else ()) if term_matches(term, text)
        ]
        age_days = item_age_days(item=item, context=context)
        source_score = RANK_SCORES.get(item.source.rank_group, 0.5)
        relevance_score = min(
            1.0,
            (0.55 if company_matches else 0.2 if body_company_matches else 0.0)
            + (0.25 if industry_matches else 0.0)
            + (0.2 if market_matches else 0.0)
            + (0.15 if source_score >= 0.8 else 0.05)
            - (0.4 if excluded_matches else 0.0),
        )

        if low_information_title(title_text=title_text, company=company):
            decision = "rejected"
            reasons.append("low_information_navigation_title")
        elif ambiguous_company_conflict(
            company=company,
            title_text=title_text,
        ):
            decision = "rejected"
            reasons.append("ambiguous_company_name_conflict")
        elif excluded_matches and not company_matches and not body_company_matches:
            decision = "rejected"
            reasons.append("negative_keyword_without_company_signal")
        elif (
            self.max_age_days is not None
            and age_days is not None
            and age_days > self.max_age_days
        ):
            decision = "rejected"
            reasons.append(f"outside_{self.max_age_days}_day_window")
        elif company_matches and (
            industry_matches or program_matches or item.source.rank_group == "official"
        ):
            decision = "published"
            reasons.append(
                "title_program_match"
                if program_matches and not industry_matches
                else "title_company_and_industry_match"
            )
        elif is_china_company(company) and company_matches:
            decision = "published"
            reasons.append("china_title_company_match")
        elif is_china_company(company) and body_company_matches and market_matches:
            decision = "published"
            reasons.append("china_body_company_market_match")
        elif company_matches or body_company_matches:
            decision = "watchlist"
            reasons.append(
                "company_match_without_industry_context"
                if company_matches
                else "body_only_company_match"
            )
        else:
            decision = "rejected"
            reasons.append("missing_company_signal")

        metadata = dict(item.metadata)
        metadata.update(
            {
                "canonical_url": canonical_url,
                "quality_decision": decision,
                "company_relevance_score": round(relevance_score, 3),
                "source_quality_score": source_score,
                "company_match_terms": company_matches[:8],
                "program_match_terms": program_matches[:8],
                "body_company_match_terms": body_company_matches[:8],
                "industry_match_terms": industry_matches[:8],
                "market_match_terms": market_matches[:8],
                "quality_reason_codes": reasons,
                "event_id": event_id(item.title),
                "event_type": classify_event_type(text),
            }
        )
        return replace(item, url=canonical_url, metadata=metadata), decision, reasons


def strong_company_terms(company: Company | None) -> tuple[str, ...]:
    if company is None:
        return ()
    values = (
        company.canonical_name,
        *company.aliases,
        *company.primary_programs,
        *company.keywords_include,
    )
    terms = []
    seen = set()
    for value in values:
        normalized = normalize_text(value)
        if not normalized or normalized in GENERIC_TERMS or len(normalized) < 3:
            continue
        if normalized not in seen:
            seen.add(normalized)
            terms.append(normalized)
    return tuple(terms)


def strong_program_terms(company: Company | None) -> tuple[str, ...]:
    if company is None:
        return ()
    terms = []
    for value in company.primary_programs:
        normalized = normalize_text(value)
        if normalized and normalized not in GENERIC_TERMS and len(normalized) >= 3:
            terms.append(normalized)
    return tuple(dict.fromkeys(terms))


def is_china_company(company: Company | None) -> bool:
    if company is None:
        return False
    region = normalize_text(company.country_or_region)
    return region in {"china", "cn", "中国", "中国大陆"}


def low_information_title(*, title_text: str, company: Company | None) -> bool:
    if any(marker in title_text for marker in LOW_INFORMATION_TITLE_MARKERS):
        return True
    if company is None:
        return False
    company_names = {
        normalize_text(value)
        for value in (company.canonical_name, *company.aliases)
        if normalize_text(value)
    }
    return title_text in company_names or normalized_title(title_text) in company_names


def ambiguous_company_conflict(*, company: Company | None, title_text: str) -> bool:
    if company is None or company.id != "i_space":
        return False
    ambiguous_signal = term_matches("ispace", title_text) or term_matches("i-space", title_text)
    moon_signal = term_matches("moon", title_text) or term_matches("lunar", title_text)
    china_identity = any(
        term_matches(term, title_text)
        for term in ("星际荣耀", "双曲线", "hyperbola", "sqx")
    )
    return ambiguous_signal and moon_signal and not china_identity


def canonicalize_url(url: str) -> str:
    try:
        parsed = urllib.parse.urlsplit(url.strip())
    except ValueError:
        return url.strip()
    query = [
        (key, value)
        for key, value in urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
        if not key.lower().startswith("utm_")
        and key.lower() not in {"gclid", "fbclid", "ref", "referrer", "source"}
    ]
    hostname = (parsed.hostname or "").lower()
    netloc = hostname
    if parsed.port and not ((parsed.scheme == "http" and parsed.port == 80) or (parsed.scheme == "https" and parsed.port == 443)):
        netloc = f"{hostname}:{parsed.port}"
    path = re.sub(r"/{2,}", "/", parsed.path or "/")
    if path != "/":
        path = path.rstrip("/")
    return urllib.parse.urlunsplit(
        ((parsed.scheme or "https").lower(), netloc, path, urllib.parse.urlencode(query), "")
    )


def deduplicate_items(items: list[NewsItem]) -> tuple[list[NewsItem], int]:
    kept: list[NewsItem] = []
    duplicate_count = 0
    seen_urls: set[tuple[str, str]] = set()
    normalized_titles: dict[str, list[str]] = {}
    for item in sorted(items, key=item_rank, reverse=True):
        url_key = (item.company_id, canonicalize_url(item.url))
        title = normalized_title(item.title)
        existing_titles = normalized_titles.setdefault(item.company_id, [])
        if url_key in seen_urls or any(title_similarity(title, other) >= 0.9 for other in existing_titles):
            duplicate_count += 1
            continue
        seen_urls.add(url_key)
        existing_titles.append(title)
        kept.append(item)
    return kept, duplicate_count


def item_rank(item: NewsItem) -> tuple[float, float, str]:
    quality = float(item.metadata.get("source_quality_score") or 0)
    relevance = float(item.metadata.get("company_relevance_score") or 0)
    published = item.published_at.isoformat() if item.published_at else ""
    return quality, relevance, published


def normalized_title(value: str) -> str:
    text = normalize_text(value)
    text = re.sub(r"\s+[-|–—]\s+[^-|–—]{2,40}$", "", text)
    return re.sub(r"[^\w\u4e00-\u9fff]+", " ", text).strip()


def title_similarity(left: str, right: str) -> float:
    if not left or not right:
        return 0.0
    return SequenceMatcher(None, left, right).ratio()


def event_id(title: str) -> str:
    return hashlib.sha1(normalized_title(title).encode("utf-8")).hexdigest()[:16]


def item_age_days(*, item: NewsItem, context: PipelineContext) -> int | None:
    if item.published_at is None:
        return None
    published = item.published_at
    if published.tzinfo is None:
        published = published.replace(tzinfo=timezone.utc)
    return max(0, (context.started_at.astimezone(timezone.utc) - published.astimezone(timezone.utc)).days)


def term_matches(term: str, normalized_text_value: str) -> bool:
    normalized = normalize_text(term)
    if not normalized:
        return False
    if re.search(r"[\u4e00-\u9fff]", normalized):
        return normalized in normalized_text_value
    return re.search(rf"(?<![a-z0-9]){re.escape(normalized)}(?![a-z0-9])", normalized_text_value) is not None


def context_term_matches(term: str, normalized_text_value: str) -> bool:
    normalized = normalize_text(term)
    if normalized in {"launch", "satellite", "rocket", "constellation", "contract"}:
        return (
            re.search(
                rf"(?<![a-z0-9]){re.escape(normalized)}[a-z]*(?![a-z0-9])",
                normalized_text_value,
            )
            is not None
        )
    return term_matches(normalized, normalized_text_value)


def normalize_text(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", str(value)).casefold().split())
