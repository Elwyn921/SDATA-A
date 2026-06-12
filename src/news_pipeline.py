#!/usr/bin/env python3
"""GitHub-native RSS/Atom news intelligence pipeline."""

from __future__ import annotations

import argparse
import datetime as dt
import email.utils
import hashlib
import html
import json
import logging
import os
import re
import sys
import textwrap
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
import zipfile
from html.parser import HTMLParser
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional, Tuple
from xml.sax.saxutils import escape


ATOM_NS = "{http://www.w3.org/2005/Atom}"
USER_AGENT = "SDATA-A GitHub-Native News Intelligence Pipeline/1.0"
RAW_ARTICLE_SCHEMA_VERSION = "raw_article.v1"
RETRYABLE_STATUS_CODES = {408, 425, 429, 500, 502, 503, 504}
LOGGER = logging.getLogger("news_pipeline")
DEFAULT_API_KEY_ENVS = {"newsapi": "NEWSAPI_KEY", "serpapi": "SERPAPI_KEY"}
DEFAULT_EVENT_CATEGORIES = [
    {
        "id": "product_launch",
        "label": "Product Launch",
        "keywords": ["launch", "release", "feature", "integration", "model", "upgrade", "available"],
    },
    {
        "id": "funding_finance",
        "label": "Funding & Finance",
        "keywords": ["funding", "ipo", "earnings", "valuation", "acquisition", "merger", "market"],
    },
    {
        "id": "policy_regulation",
        "label": "Policy & Regulation",
        "keywords": ["law", "policy", "regulation", "tariff", "sanctions", "compliance", "ruling"],
    },
    {
        "id": "security_risk",
        "label": "Security & Risk",
        "keywords": ["security", "breach", "vulnerability", "outage", "risk", "safety", "incident"],
    },
    {
        "id": "research_technical",
        "label": "Research & Technical",
        "keywords": ["research", "paper", "benchmark", "architecture", "technical", "developer"],
    },
    {
        "id": "supply_chain_operations",
        "label": "Supply Chain & Operations",
        "keywords": ["supply chain", "shipping", "logistics", "manufacturing", "inventory", "semiconductor"],
    },
    {
        "id": "company_strategy",
        "label": "Company Strategy",
        "keywords": ["partnership", "strategy", "restructuring", "layoff", "hiring", "executive"],
    },
]


def utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def load_config(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def setup_logging(log_file: Optional[Path] = None) -> None:
    handlers: List[logging.Handler] = [logging.StreamHandler()]
    if log_file:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        handlers.append(logging.FileHandler(log_file, encoding="utf-8"))
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=handlers,
        force=True,
    )


def validate_config(config: dict) -> None:
    sources = config.get("sources")
    if not isinstance(sources, list):
        raise ValueError("Config must define a sources list.")
    for source in sources:
        source_type = source.get("type", "rss")
        required_fields = ["id", "name"]
        if source_type in ("rss", "atom", "feed", "official_website", "website"):
            required_fields.append("url")
        elif source_type in ("gdelt", "newsapi", "serpapi"):
            required_fields.append("query")
        else:
            required_fields.append("type")
        missing = [field for field in required_fields if not source.get(field)]
        if missing:
            source_label = source.get("id") or source.get("name") or "<unknown>"
            raise ValueError(f"Source {source_label} is missing required field(s): {', '.join(missing)}")


def required_env_vars(config: dict) -> List[str]:
    required = config.get("pipeline", {}).get("required_env", [])
    if not isinstance(required, list):
        raise ValueError("pipeline.required_env must be a list when provided.")
    return [str(name) for name in required if str(name).strip()]


def missing_required_env(config: dict, environ: Optional[dict] = None) -> List[str]:
    env = environ if environ is not None else os.environ
    required = required_env_vars(config)
    for source in config.get("sources", []):
        if not source.get("enabled", True) or source.get("api_key"):
            continue
        default_env_name = DEFAULT_API_KEY_ENVS.get(source.get("type", ""))
        env_name = source.get("api_key_env") or default_env_name
        if env_name:
            required.append(env_name)
    return [name for name in dict.fromkeys(required) if not env.get(name)]


class RateLimiter:
    def __init__(
        self,
        min_interval_seconds: float = 0.0,
        sleeper: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.min_interval_seconds = max(0.0, float(min_interval_seconds))
        self.sleeper = sleeper
        self.clock = clock
        self._last_request_at: Optional[float] = None

    def wait(self) -> None:
        if self.min_interval_seconds <= 0:
            return
        now = self.clock()
        if self._last_request_at is not None:
            elapsed = now - self._last_request_at
            if elapsed < self.min_interval_seconds:
                self.sleeper(self.min_interval_seconds - elapsed)
                now = self.clock()
        self._last_request_at = now


class HTTPClient:
    def __init__(
        self,
        timeout: int = 20,
        retries: int = 2,
        backoff_seconds: float = 1.0,
        rate_limit_seconds: float = 0.0,
        sleeper: Callable[[float], None] = time.sleep,
        opener: Callable = urllib.request.urlopen,
    ) -> None:
        self.timeout = timeout
        self.retries = max(0, retries)
        self.backoff_seconds = max(0.0, float(backoff_seconds))
        self.sleeper = sleeper
        self.opener = opener
        self.rate_limiter = RateLimiter(rate_limit_seconds, sleeper=sleeper)

    def request_bytes(
        self,
        url: str,
        params: Optional[dict] = None,
        headers: Optional[dict] = None,
        timeout: Optional[int] = None,
    ) -> bytes:
        full_url = with_query_params(url, params or {})
        request_headers = {"User-Agent": USER_AGENT, "Accept": "*/*"}
        request_headers.update(headers or {})
        last_error: Optional[BaseException] = None

        for attempt in range(self.retries + 1):
            self.rate_limiter.wait()
            request = urllib.request.Request(full_url, headers=request_headers)
            try:
                response = self.opener(request, timeout=timeout or self.timeout)
                try:
                    return response.read()
                finally:
                    close = getattr(response, "close", None)
                    if callable(close):
                        close()
            except urllib.error.HTTPError as exc:
                last_error = exc
                if not self._should_retry_http(exc, attempt):
                    raise
                self.sleeper(self._retry_delay(exc, attempt))
            except (urllib.error.URLError, TimeoutError) as exc:
                last_error = exc
                if attempt >= self.retries:
                    raise
                self.sleeper(self._retry_delay(None, attempt))

        if last_error:
            raise last_error
        raise RuntimeError("HTTP request failed without an exception")

    def request_json(
        self,
        url: str,
        params: Optional[dict] = None,
        headers: Optional[dict] = None,
        timeout: Optional[int] = None,
    ) -> dict:
        payload = self.request_bytes(
            url,
            params=params,
            headers={"Accept": "application/json", **(headers or {})},
            timeout=timeout,
        )
        return json.loads(payload.decode("utf-8"))

    def _should_retry_http(self, exc: urllib.error.HTTPError, attempt: int) -> bool:
        return attempt < self.retries and exc.code in RETRYABLE_STATUS_CODES

    def _retry_delay(self, exc: Optional[urllib.error.HTTPError], attempt: int) -> float:
        if exc is not None:
            retry_after = exc.headers.get("Retry-After") if exc.headers else None
            if retry_after:
                try:
                    return max(0.0, float(retry_after))
                except ValueError:
                    try:
                        parsed = email.utils.parsedate_to_datetime(retry_after)
                        if parsed.tzinfo is None:
                            parsed = parsed.replace(tzinfo=dt.timezone.utc)
                        return max(0.0, (parsed - utc_now()).total_seconds())
                    except (TypeError, ValueError, IndexError):
                        pass
        return self.backoff_seconds * (2**attempt)


def with_query_params(url: str, params: dict) -> str:
    clean_params = {key: value for key, value in params.items() if value not in (None, "", [])}
    if not clean_params:
        return url
    parsed = urllib.parse.urlparse(url)
    existing = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
    query = urllib.parse.urlencode(existing + list(clean_params.items()), doseq=True)
    return urllib.parse.urlunparse(parsed._replace(query=query))


def http_from_config(config: dict) -> HTTPClient:
    pipeline = config.get("pipeline", {})
    return HTTPClient(
        timeout=int(pipeline.get("request_timeout_seconds", 20)),
        retries=int(pipeline.get("request_retries", 2)),
        backoff_seconds=float(pipeline.get("request_backoff_seconds", 1.0)),
        rate_limit_seconds=float(pipeline.get("rate_limit_seconds", 0.0)),
    )


def fetch_xml(url: str, timeout: int = 20) -> bytes:
    return HTTPClient(timeout=timeout).request_bytes(url)


def parse_datetime(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    value = value.strip()
    relative = parse_relative_datetime(value)
    if relative:
        return relative
    try:
        parsed = email.utils.parsedate_to_datetime(value)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=dt.timezone.utc)
        return parsed.astimezone(dt.timezone.utc).isoformat()
    except (TypeError, ValueError, IndexError):
        pass
    try:
        normalized = value.replace("Z", "+00:00")
        parsed = dt.datetime.fromisoformat(normalized)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=dt.timezone.utc)
        return parsed.astimezone(dt.timezone.utc).isoformat()
    except ValueError:
        pass
    for fmt in ("%Y%m%d%H%M%S", "%Y%m%dT%H%M%SZ", "%Y%m%d"):
        try:
            parsed = dt.datetime.strptime(value, fmt).replace(tzinfo=dt.timezone.utc)
            return parsed.isoformat()
        except ValueError:
            continue
    return None


def parse_relative_datetime(value: str) -> Optional[str]:
    match = re.match(
        r"^\s*(\d+)\s+(minute|hour|day|week|month|year)s?\s+ago\s*$",
        value,
        flags=re.IGNORECASE,
    )
    if not match:
        return None
    amount = int(match.group(1))
    unit = match.group(2).lower()
    if unit == "minute":
        delta = dt.timedelta(minutes=amount)
    elif unit == "hour":
        delta = dt.timedelta(hours=amount)
    elif unit == "day":
        delta = dt.timedelta(days=amount)
    elif unit == "week":
        delta = dt.timedelta(weeks=amount)
    elif unit == "month":
        delta = dt.timedelta(days=amount * 30)
    else:
        delta = dt.timedelta(days=amount * 365)
    return (utc_now() - delta).isoformat()


def clean_text(value: Optional[str]) -> str:
    if not value:
        return ""
    value = re.sub(r"<[^>]+>", " ", value)
    value = html.unescape(value)
    return re.sub(r"\s+", " ", value).strip()


def canonical_url(url: Optional[str]) -> str:
    if not url:
        return ""
    url = url.strip()
    parsed = urllib.parse.urlparse(url)
    if not parsed.scheme:
        return url
    return urllib.parse.urlunparse(parsed._replace(fragment=""))


def text_of(element: Optional[ET.Element], child_name: str) -> str:
    if element is None:
        return ""
    child = element.find(child_name)
    return clean_text(child.text if child is not None else "")


def text_of_any(element: Optional[ET.Element], child_names: Iterable[str]) -> str:
    if element is None:
        return ""
    wanted = set(child_names)
    for child in list(element):
        local_name = child.tag.split("}", 1)[-1] if "}" in child.tag else child.tag
        if child.tag in wanted or local_name in wanted:
            return clean_text(child.text or "")
    return ""


def build_raw_article(
    source: dict,
    title: str,
    url: str,
    summary: str = "",
    published_at: Optional[str] = None,
    *,
    author: str = "",
    content: str = "",
    updated_at: Optional[str] = None,
    language: str = "",
    country: str = "",
    image_url: str = "",
    raw_source: str = "",
    raw: Optional[dict] = None,
    metadata: Optional[dict] = None,
) -> dict:
    clean_title = clean_text(title)
    clean_url = canonical_url(url)
    clean_summary = clean_text(summary)
    stable_basis = clean_url or f"{source['id']}:{clean_title}:{published_at or ''}"
    item_id = hashlib.sha256(stable_basis.encode("utf-8")).hexdigest()[:16]
    return {
        "id": item_id,
        "schema_version": RAW_ARTICLE_SCHEMA_VERSION,
        "source_id": source["id"],
        "source_name": source["name"],
        "source_type": source.get("type", "rss"),
        "trust_tier": int(source.get("trust_tier", 3)),
        "fetcher": source.get("type", "rss"),
        "title": clean_title,
        "url": clean_url,
        "summary": clean_summary,
        "content": clean_text(content),
        "author": clean_text(author),
        "published_at": published_at,
        "updated_at": updated_at,
        "collected_at": utc_now().isoformat(),
        "language": language or source.get("language", ""),
        "country": country or source.get("country", ""),
        "image_url": canonical_url(image_url),
        "raw_source": raw_source or source.get("type", "rss"),
        "raw": raw or {},
        "metadata": metadata or {},
    }


def parse_rss(root: ET.Element, source: dict) -> List[dict]:
    items = []
    for item in root.findall("./channel/item"):
        title = text_of_any(item, ["title"])
        link = text_of_any(item, ["link"])
        summary = text_of_any(item, ["description", "summary"])
        published = parse_datetime(text_of_any(item, ["pubDate", "date", "published"]))
        items.append(normalize_item(source, title, link, summary, published))
    return items


def parse_atom(root: ET.Element, source: dict) -> List[dict]:
    items = []
    for entry in root.findall(f"./{ATOM_NS}entry"):
        title = clean_text((entry.findtext(f"{ATOM_NS}title") or ""))
        summary = clean_text(entry.findtext(f"{ATOM_NS}summary") or entry.findtext(f"{ATOM_NS}content") or "")
        published = parse_datetime(
            entry.findtext(f"{ATOM_NS}published") or entry.findtext(f"{ATOM_NS}updated")
        )
        link = ""
        for link_node in entry.findall(f"{ATOM_NS}link"):
            rel = link_node.attrib.get("rel", "alternate")
            if rel == "alternate" and link_node.attrib.get("href"):
                link = link_node.attrib["href"]
                break
        items.append(normalize_item(source, title, link, summary, published))
    return items


def normalize_item(
    source: dict, title: str, link: str, summary: str, published_at: Optional[str]
) -> dict:
    return build_raw_article(source, title, link, summary, published_at, raw_source="feed")


def parse_feed(xml_bytes: bytes, source: dict) -> List[dict]:
    root = ET.fromstring(xml_bytes)
    tag = root.tag.lower()
    if tag.endswith("rss"):
        return parse_rss(root, source)
    if tag == f"{ATOM_NS}feed":
        return parse_atom(root, source)
    raise ValueError(f"Unsupported feed root: {root.tag}")


class OfficialWebsiteParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title_parts: List[str] = []
        self.meta: Dict[str, str] = {}
        self.anchors: List[Tuple[str, str]] = []
        self._in_title = False
        self._anchor_stack: List[Tuple[str, List[str]]] = []

    def handle_starttag(self, tag: str, attrs: List[Tuple[str, Optional[str]]]) -> None:
        attrs_dict = {key.lower(): value or "" for key, value in attrs}
        if tag.lower() == "title":
            self._in_title = True
        elif tag.lower() == "meta":
            name = (attrs_dict.get("property") or attrs_dict.get("name") or "").lower()
            content = attrs_dict.get("content", "")
            if name and content:
                self.meta[name] = clean_text(content)
        elif tag.lower() == "a" and attrs_dict.get("href"):
            self._anchor_stack.append((attrs_dict["href"], []))

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self.title_parts.append(data)
        for _, chunks in self._anchor_stack:
            chunks.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "title":
            self._in_title = False
        elif tag.lower() == "a" and self._anchor_stack:
            href, chunks = self._anchor_stack.pop()
            self.anchors.append((href, clean_text(" ".join(chunks))))

    @property
    def page_title(self) -> str:
        return clean_text(" ".join(self.title_parts))


def fetch_rss(source: dict, http_client: HTTPClient) -> List[dict]:
    return parse_feed(http_client.request_bytes(source["url"]), source)


def fetch_official_website(source: dict, http_client: HTTPClient) -> List[dict]:
    html_bytes = http_client.request_bytes(source["url"], headers={"Accept": "text/html,*/*"})
    parser = OfficialWebsiteParser()
    parser.feed(html_bytes.decode(source.get("encoding", "utf-8"), errors="replace"))
    base_url = source["url"]
    max_items = int(source.get("max_items", 30))
    include_patterns = compile_patterns(source.get("include_patterns") or source.get("article_patterns") or [])
    exclude_patterns = compile_patterns(source.get("exclude_patterns") or [])
    require_same_domain = bool(source.get("same_domain", True))
    base_host = urllib.parse.urlparse(base_url).netloc.lower()
    seen = set()
    items = []

    for href, label in parser.anchors:
        absolute_url = canonical_url(urllib.parse.urljoin(base_url, href))
        if not is_fetchable_article_url(absolute_url):
            continue
        if require_same_domain and urllib.parse.urlparse(absolute_url).netloc.lower() != base_host:
            continue
        if include_patterns and not any(pattern.search(absolute_url) for pattern in include_patterns):
            continue
        if exclude_patterns and any(pattern.search(absolute_url) for pattern in exclude_patterns):
            continue
        title = label or parser.meta.get("og:title", "") or parser.page_title
        if len(title) < int(source.get("min_title_length", 4)):
            continue
        if absolute_url in seen:
            continue
        seen.add(absolute_url)
        items.append(
            build_raw_article(
                source,
                title,
                absolute_url,
                parser.meta.get("og:description", "") or parser.meta.get("description", ""),
                raw_source="official_website",
                metadata={"homepage": base_url},
            )
        )
        if len(items) >= max_items:
            break

    if not items and (parser.meta.get("og:title") or parser.page_title):
        items.append(
            build_raw_article(
                source,
                parser.meta.get("og:title", "") or parser.page_title,
                parser.meta.get("og:url", "") or base_url,
                parser.meta.get("og:description", "") or parser.meta.get("description", ""),
                raw_source="official_website",
                metadata={"homepage": base_url, "fallback": "page_metadata"},
            )
        )
    return items


def compile_patterns(patterns: Iterable[str]) -> List[re.Pattern]:
    return [re.compile(pattern) for pattern in patterns]


def is_fetchable_article_url(url: str) -> bool:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in ("http", "https"):
        return False
    lowered = url.lower()
    blocked_extensions = (".pdf", ".zip", ".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".mp4")
    return not lowered.endswith(blocked_extensions)


def fetch_gdelt(source: dict, http_client: HTTPClient) -> List[dict]:
    endpoint = source.get("endpoint", "https://api.gdeltproject.org/api/v2/doc/doc")
    params = {
        "query": source["query"],
        "mode": source.get("mode", "ArtList"),
        "format": "json",
        "maxrecords": int(source.get("max_items", 50)),
        "sort": source.get("sort", "HybridRel"),
    }
    params.update(source.get("params", {}))
    payload = http_client.request_json(endpoint, params=params)
    articles = payload.get("articles", [])
    return [
        build_raw_article(
            source,
            article.get("title", ""),
            article.get("url", ""),
            article.get("summary", "") or article.get("snippet", ""),
            parse_datetime(article.get("seendate") or article.get("publishedAt")),
            language=article.get("language", ""),
            country=article.get("sourceCountry", ""),
            image_url=article.get("socialimage", ""),
            raw_source="gdelt",
            raw=article,
            metadata={"domain": article.get("domain", "")},
        )
        for article in articles
        if article.get("title") and article.get("url")
    ]


def fetch_newsapi(source: dict, http_client: HTTPClient) -> List[dict]:
    endpoint = source.get("endpoint", "https://newsapi.org/v2/everything")
    api_key = api_key_for(source, "NEWSAPI_KEY")
    params = {
        "apiKey": api_key,
        "q": source["query"],
        "language": source.get("language", "en"),
        "pageSize": int(source.get("max_items", 50)),
        "sortBy": source.get("sort_by", "publishedAt"),
    }
    if source.get("domains"):
        params["domains"] = ",".join(source["domains"])
    params.update(source.get("params", {}))
    payload = http_client.request_json(endpoint, params=params)
    if payload.get("status") == "error":
        raise ValueError(payload.get("message", "NewsAPI returned an error"))
    items = []
    for article in payload.get("articles", []):
        publisher = article.get("source") or {}
        items.append(
            build_raw_article(
                source,
                article.get("title", ""),
                article.get("url", ""),
                article.get("description", ""),
                parse_datetime(article.get("publishedAt")),
                author=article.get("author", ""),
                content=article.get("content", ""),
                image_url=article.get("urlToImage", ""),
                raw_source="newsapi",
                raw=article,
                metadata={"publisher": publisher.get("name", ""), "publisher_id": publisher.get("id", "")},
            )
        )
    return [item for item in items if item["title"] and item["url"]]


def fetch_serpapi(source: dict, http_client: HTTPClient) -> List[dict]:
    endpoint = source.get("endpoint", "https://serpapi.com/search.json")
    api_key = api_key_for(source, "SERPAPI_KEY")
    params = {
        "api_key": api_key,
        "engine": source.get("engine", "google_news"),
        "q": source["query"],
        "num": int(source.get("max_items", 50)),
    }
    params.update(source.get("params", {}))
    payload = http_client.request_json(endpoint, params=params)
    if payload.get("error"):
        raise ValueError(payload["error"])
    items = []
    for article in payload.get("news_results", []):
        publisher = article.get("source")
        if isinstance(publisher, dict):
            publisher_name = publisher.get("name", "")
        else:
            publisher_name = publisher or ""
        items.append(
            build_raw_article(
                source,
                article.get("title", ""),
                article.get("link", ""),
                article.get("snippet", ""),
                parse_datetime(article.get("date")),
                image_url=article.get("thumbnail", ""),
                raw_source="serpapi",
                raw=article,
                metadata={"publisher": publisher_name},
            )
        )
    return [item for item in items if item["title"] and item["url"]]


def api_key_for(source: dict, default_env_name: str) -> str:
    env_name = source.get("api_key_env", default_env_name)
    api_key = source.get("api_key") or os.environ.get(env_name)
    if not api_key:
        raise ValueError(f"Missing API key. Set {env_name} or disable source {source['id']}.")
    return api_key


FETCHERS = {
    "rss": fetch_rss,
    "atom": fetch_rss,
    "feed": fetch_rss,
    "official_website": fetch_official_website,
    "website": fetch_official_website,
    "gdelt": fetch_gdelt,
    "newsapi": fetch_newsapi,
    "serpapi": fetch_serpapi,
}


def topic_hits(item: dict, topics: List[dict]) -> Tuple[List[str], int]:
    haystack = f"{item.get('title', '')} {item.get('summary', '')}".lower()
    matched = []
    score = 0
    for topic in topics:
        hits = [keyword for keyword in topic["keywords"] if keyword.lower() in haystack]
        if hits:
            matched.append(topic["id"])
            score += len(hits) * 4
    return matched, score


def classify_event(item: dict, categories: List[dict]) -> dict:
    haystack = f"{item.get('title', '')} {item.get('summary', '')}".lower()
    selected = {"id": "general_update", "label": "General Update", "keywords": []}
    selected_hits = 0
    for category in categories:
        hits = sum(1 for keyword in category.get("keywords", []) if keyword.lower() in haystack)
        if hits > selected_hits:
            selected = category
            selected_hits = hits
    return {
        "event_category": selected["id"],
        "event_category_label": selected.get("label", selected["id"].replace("_", " ").title()),
        "event_category_hits": selected_hits,
    }


def priority_from_importance(score: int) -> str:
    if score >= 70:
        return "high"
    if score >= 40:
        return "medium"
    return "low"


def summarize_item(item: dict) -> str:
    summary = item.get("summary") or item.get("title") or ""
    return textwrap.shorten(summary, width=180, placeholder="...")


def why_it_matters(item: dict) -> str:
    category = item.get("event_category_label", "General Update")
    topics = ", ".join(item.get("topics", [])) if item.get("topics") else "unclassified topics"
    return (
        f"{category} signal tagged as {topics}; priority is {item.get('priority', 'low')} "
        "based on source trust, recency, and keyword relevance."
    )


def recommended_action(item: dict) -> str:
    if item.get("priority") == "high":
        return "Review this week and decide whether follow-up analysis or stakeholder notification is needed."
    if item.get("priority") == "medium":
        return "Monitor for corroborating signals and include in the next weekly review."
    return "Archive as context unless related signals increase."


def enrich_items(items: Iterable[dict], topics: List[dict], categories: Optional[List[dict]] = None) -> List[dict]:
    enriched = []
    categories = categories or DEFAULT_EVENT_CATEGORIES
    for item in items:
        matched_topics, keyword_score = topic_hits(item, topics)
        event = classify_event(item, categories)
        trust_bonus = max(0, 4 - int(item.get("trust_tier", 3))) * 2
        recency_bonus = 0
        if item.get("published_at"):
            try:
                published = dt.datetime.fromisoformat(item["published_at"])
                age_hours = (utc_now() - published).total_seconds() / 3600
                recency_bonus = 8 if age_hours <= 24 else 3 if age_hours <= 72 else 0
            except ValueError:
                recency_bonus = 0
        score = keyword_score + trust_bonus + recency_bonus + (event["event_category_hits"] * 3)
        importance_score = min(100, max(0, score * 5))
        priority = priority_from_importance(importance_score)
        row = {
            **item,
            **event,
            "topics": matched_topics,
            "intelligence_score": score,
            "importance_score": importance_score,
            "priority": priority,
        }
        row["one_sentence_summary"] = summarize_item(row)
        row["why_it_matters"] = why_it_matters(row)
        row["recommended_action"] = recommended_action(row)
        enriched.append(row)
    return sorted(enriched, key=lambda row: row["importance_score"], reverse=True)


def dedupe_items(items: Iterable[dict]) -> List[dict]:
    seen = set()
    unique = []
    for item in items:
        key = item.get("url") or item.get("title", "").lower()
        if not key or key in seen:
            continue
        seen.add(key)
        unique.append(item)
    return unique


def collect(
    config: dict, fixture: Optional[Path] = None, http_client: Optional[HTTPClient] = None
) -> Tuple[List[dict], List[dict]]:
    items = []
    errors = []
    http_client = http_client or http_from_config(config)
    sources = [source for source in config["sources"] if source.get("enabled", True)]
    LOGGER.info("Collecting from %s enabled source(s)", len(sources))
    for source in sources:
        source_type = source.get("type", "rss")
        try:
            LOGGER.info("Fetching source %s (%s) with %s fetcher", source["id"], source["name"], source_type)
            if fixture:
                if source_type not in ("rss", "atom", "feed"):
                    LOGGER.info("Skipping non-feed source %s during fixture run", source["id"])
                    continue
                parsed_items = parse_feed(fixture.read_bytes(), source)
            else:
                fetcher = FETCHERS.get(source_type)
                if fetcher is None:
                    raise ValueError(f"Unsupported source type: {source_type}")
                parsed_items = fetcher(source, http_client)
            LOGGER.info("Parsed %s item(s) from %s", len(parsed_items), source["id"])
            items.extend(parsed_items)
        except (
            OSError,
            urllib.error.URLError,
            TimeoutError,
            ET.ParseError,
            ValueError,
            json.JSONDecodeError,
        ) as exc:
            LOGGER.warning("Source %s failed: %s", source.get("id", "<unknown>"), exc)
            errors.append(
                {
                    "source_id": source["id"],
                    "source_name": source["name"],
                    "source_type": source_type,
                    "error": str(exc),
                }
            )
    return dedupe_items(items), errors


def write_jsonl(path: Path, rows: Iterable[dict]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def render_report(items: List[dict], errors: List[dict], run_id: str) -> str:
    top_items = items[:20]
    lines = [
        f"# News Intelligence Brief - {run_id}",
        "",
        f"- Collected items: {len(items)}",
        f"- High priority: {sum(1 for item in items if item['priority'] == 'high')}",
        f"- Medium priority: {sum(1 for item in items if item['priority'] == 'medium')}",
        f"- Source errors: {len(errors)}",
        "",
        "## Top Signals",
        "",
    ]
    if not top_items:
        lines.append("No items collected.")
    for index, item in enumerate(top_items, start=1):
        topics = ", ".join(item["topics"]) if item["topics"] else "unclassified"
        url = item["url"] or "#"
        summary = textwrap.shorten(item.get("summary") or "", width=220, placeholder="...")
        lines.extend(
            [
                f"{index}. [{item['title']}]({url})",
                f"   - Source: {item['source_name']} | Category: {item['event_category_label']} | Priority: {item['priority']} | Importance: {item['importance_score']} | Topics: {topics}",
                f"   - Published: {item.get('published_at') or 'unknown'}",
                f"   - Why it matters: {item['why_it_matters']}",
                f"   - Action: {item['recommended_action']}",
            ]
        )
        if summary:
            lines.append(f"   - Note: {summary}")
    if errors:
        lines.extend(["", "## Source Errors", ""])
        for error in errors:
            lines.append(f"- {error['source_name']}: {error['error']}")
    lines.append("")
    return "\n".join(lines)


def render_weekly_report(items: List[dict], errors: List[dict], run_id: str) -> str:
    now = utc_now()
    iso_year, iso_week, _ = now.isocalendar()
    lines = [
        f"# Weekly News Report - {iso_year}-W{iso_week:02d}",
        "",
        f"- Run ID: {run_id}",
        f"- Generated at: {now.isoformat()}",
        f"- Total items: {len(items)}",
        f"- High priority: {sum(1 for item in items if item['priority'] == 'high')}",
        f"- Medium priority: {sum(1 for item in items if item['priority'] == 'medium')}",
        f"- Low priority: {sum(1 for item in items if item['priority'] == 'low')}",
        f"- Source errors: {len(errors)}",
        "",
        "## Executive Summary",
        "",
    ]
    if items:
        top_categories = {}
        for item in items:
            top_categories[item["event_category_label"]] = top_categories.get(item["event_category_label"], 0) + 1
        category_summary = ", ".join(
            f"{category} ({count})" for category, count in sorted(top_categories.items(), key=lambda row: row[1], reverse=True)
        )
        lines.append(f"The strongest signals this week concentrate in {category_summary}.")
    else:
        lines.append("No usable items were collected this week.")

    lines.extend(["", "## Priority Signals", ""])
    for item in items[:10]:
        topics = ", ".join(item["topics"]) if item["topics"] else "unclassified"
        lines.extend(
            [
                f"### {item['title']}",
                "",
                f"- Source: {item['source_name']}",
                f"- Category: {item['event_category_label']}",
                f"- Priority: {item['priority']} ({item['importance_score']}/100)",
                f"- Topics: {topics}",
                f"- Summary: {item['one_sentence_summary']}",
                f"- Why it matters: {item['why_it_matters']}",
                f"- Recommended action: {item['recommended_action']}",
                f"- URL: {item['url'] or '#'}",
                "",
            ]
        )
    if errors:
        lines.extend(["## Source Errors", ""])
        for error in errors:
            lines.append(f"- {error['source_name']}: {error['error']}")
        lines.append("")
    return "\n".join(lines)


def excel_rows(items: List[dict]) -> List[List[object]]:
    rows: List[List[object]] = [
        [
            "Date",
            "Source",
            "Category",
            "Priority",
            "Score",
            "Title",
            "Summary",
            "Why It Matters",
            "Action",
            "URL",
        ]
    ]
    for item in items:
        rows.append(
            [
                item.get("published_at") or "",
                item.get("source_name") or "",
                item.get("event_category_label") or "",
                item.get("priority") or "",
                item.get("importance_score", 0),
                item.get("title") or "",
                item.get("one_sentence_summary") or "",
                item.get("why_it_matters") or "",
                item.get("recommended_action") or "",
                item.get("url") or "",
            ]
        )
    return rows


def column_name(index: int) -> str:
    name = ""
    while index:
        index, remainder = divmod(index - 1, 26)
        name = chr(65 + remainder) + name
    return name


def render_sheet_xml(rows: List[List[object]]) -> str:
    xml_rows = []
    for row_index, row in enumerate(rows, start=1):
        cells = []
        for column_index, value in enumerate(row, start=1):
            cell_ref = f"{column_name(column_index)}{row_index}"
            text = escape(str(value), {'"': "&quot;"})
            cells.append(f'<c r="{cell_ref}" t="inlineStr"><is><t>{text}</t></is></c>')
        xml_rows.append(f'<row r="{row_index}">{"".join(cells)}</row>')
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        "<sheetData>"
        + "".join(xml_rows)
        + "</sheetData></worksheet>"
    )


def write_xlsx(path: Path, items: List[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as workbook:
        workbook.writestr(
            "[Content_Types].xml",
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
            '<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
            '<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>'
            "</Types>",
        )
        workbook.writestr(
            "_rels/.rels",
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
            "</Relationships>",
        )
        workbook.writestr(
            "xl/workbook.xml",
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
            '<sheets><sheet name="News Report" sheetId="1" r:id="rId1"/></sheets></workbook>',
        )
        workbook.writestr(
            "xl/_rels/workbook.xml.rels",
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>'
            '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>'
            "</Relationships>",
        )
        workbook.writestr(
            "xl/styles.xml",
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            "<fonts count=\"1\"><font><sz val=\"11\"/><name val=\"Calibri\"/></font></fonts>"
            "<fills count=\"1\"><fill><patternFill patternType=\"none\"/></fill></fills>"
            "<borders count=\"1\"><border/></borders>"
            "<cellStyleXfs count=\"1\"><xf numFmtId=\"0\" fontId=\"0\" fillId=\"0\" borderId=\"0\"/></cellStyleXfs>"
            "<cellXfs count=\"1\"><xf numFmtId=\"0\" fontId=\"0\" fillId=\"0\" borderId=\"0\" xfId=\"0\"/></cellXfs>"
            "</styleSheet>",
        )
        workbook.writestr("xl/worksheets/sheet1.xml", render_sheet_xml(excel_rows(items)))


def render_pages_index(items: List[dict], errors: List[dict], run_id: str) -> str:
    cards = []
    for item in items[:24]:
        url = html.escape(item.get("url") or "#", quote=True)
        title = html.escape(item.get("title") or "Untitled")
        summary = html.escape(item.get("one_sentence_summary") or "")
        category = html.escape(item.get("event_category_label") or "General Update")
        priority = html.escape(item.get("priority") or "low")
        score = int(item.get("importance_score", 0))
        cards.append(
            f"""
      <article class="signal">
        <div class="meta"><span>{category}</span><strong>{priority.upper()} &middot; {score}</strong></div>
        <h2><a href="{url}">{title}</a></h2>
        <p>{summary}</p>
      </article>"""
        )
    error_note = f"<p>{len(errors)} source error(s) recorded during this run.</p>" if errors else ""
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>SDATA A News Intelligence</title>
  <style>
    body {{ margin: 0; font-family: Arial, sans-serif; color: #1f2933; background: #f7f7f4; }}
    header {{ padding: 40px 24px 24px; background: #19324a; color: white; }}
    main {{ max-width: 1120px; margin: 0 auto; padding: 24px; }}
    .summary {{ display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px; margin-top: 18px; }}
    .metric, .signal {{ background: white; border: 1px solid #d9ded8; border-radius: 8px; padding: 16px; }}
    .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 14px; }}
    .meta {{ display: flex; justify-content: space-between; gap: 12px; font-size: 12px; color: #59636e; text-transform: uppercase; }}
    h1 {{ margin: 0; font-size: 32px; letter-spacing: 0; }}
    h2 {{ font-size: 18px; line-height: 1.25; margin: 12px 0 8px; letter-spacing: 0; }}
    a {{ color: #0b5cad; text-decoration: none; }}
    p {{ line-height: 1.5; }}
    @media (max-width: 760px) {{ .summary {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }} }}
  </style>
</head>
<body>
  <header>
    <h1>SDATA A News Intelligence</h1>
    <p>Run {html.escape(run_id)} &middot; generated {html.escape(utc_now().isoformat())}</p>
  </header>
  <main>
    <section class="summary">
      <div class="metric"><strong>{len(items)}</strong><br>Total items</div>
      <div class="metric"><strong>{sum(1 for item in items if item['priority'] == 'high')}</strong><br>High priority</div>
      <div class="metric"><strong>{sum(1 for item in items if item['priority'] == 'medium')}</strong><br>Medium priority</div>
      <div class="metric"><strong>{len(errors)}</strong><br>Source errors</div>
    </section>
    {error_note}
    <section class="grid">
      {"".join(cards) if cards else "<p>No items collected.</p>"}
    </section>
  </main>
</body>
</html>
"""


def build_llm_input(config: dict, items: List[dict], run_id: str) -> dict:
    return {
        "run_id": run_id,
        "generated_at": utc_now().isoformat(),
        "topics": config.get("topics", []),
        "items": [
            {
                "id": item["id"],
                "source_name": item["source_name"],
                "trust_tier": item["trust_tier"],
                "title": item["title"],
                "url": item["url"],
                "summary": item["summary"],
                "published_at": item["published_at"],
                "topics": item["topics"],
                "intelligence_score": item["intelligence_score"],
            }
            for item in items
        ],
    }


def write_outputs(out_dir: Path, items: List[dict], errors: List[dict], run_id: str, config: dict) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    write_jsonl(out_dir / "items.jsonl", items)
    (out_dir / "report.md").write_text(render_report(items, errors, run_id), encoding="utf-8")
    (out_dir / "weekly-report.md").write_text(render_weekly_report(items, errors, run_id), encoding="utf-8")
    write_xlsx(out_dir / "news-report.xlsx", items)
    pages_dir = out_dir / "pages"
    pages_dir.mkdir(parents=True, exist_ok=True)
    (pages_dir / "index.html").write_text(render_pages_index(items, errors, run_id), encoding="utf-8")
    (out_dir / "llm-input.json").write_text(
        json.dumps(build_llm_input(config, items, run_id), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    summary = {
        "run_id": run_id,
        "generated_at": utc_now().isoformat(),
        "items": len(items),
        "high_priority": sum(1 for item in items if item["priority"] == "high"),
        "medium_priority": sum(1 for item in items if item["priority"] == "medium"),
        "low_priority": sum(1 for item in items if item["priority"] == "low"),
        "output_files": [
            "items.jsonl",
            "summary.json",
            "report.md",
            "weekly-report.md",
            "news-report.xlsx",
            "llm-input.json",
            "pages/index.html",
        ],
        "source_errors": errors,
    }
    (out_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    LOGGER.info("Wrote outputs to %s", out_dir)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=Path("config/news_sources.json"))
    parser.add_argument("--out", type=Path, default=Path("data/news/latest"))
    parser.add_argument("--max-items", type=int, default=None)
    parser.add_argument("--fixture", type=Path, default=None, help="Use a local RSS/Atom fixture for every source.")
    parser.add_argument("--log-file", type=Path, default=None, help="Write pipeline logs to this file.")
    args = parser.parse_args(argv)

    log_file = args.log_file or args.out / "pipeline.log"
    setup_logging(log_file)
    LOGGER.info("Starting news intelligence pipeline")

    try:
        config = load_config(args.config)
        validate_config(config)
        missing_env = missing_required_env(config)
        if missing_env:
            LOGGER.error("Missing required environment variable(s): %s", ", ".join(missing_env))
            return 2
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        LOGGER.error("Pipeline configuration failed: %s", exc)
        return 2

    max_items = args.max_items or int(config.get("pipeline", {}).get("max_items", 80))
    run_id = utc_now().strftime("%Y-%m-%dT%H-%M-%SZ")

    raw_items, errors = collect(config, fixture=args.fixture)
    enriched = enrich_items(
        raw_items,
        config.get("topics", []),
        config.get("event_categories", DEFAULT_EVENT_CATEGORIES),
    )[:max_items]
    try:
        write_outputs(args.out, enriched, errors, run_id, config)
    except OSError as exc:
        LOGGER.error("Failed to write outputs: %s", exc)
        return 1

    LOGGER.info("Collected %s item(s) into %s", len(enriched), args.out)
    if errors:
        LOGGER.warning("Completed with %s source error(s)", len(errors))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
