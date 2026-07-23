"""RSS provider adapter."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from typing import Any
from urllib.parse import urlencode, urlsplit

from satellite_news.provider.base import (
    ProviderHTTPClient,
    build_raw_article,
    company_override,
    dry_run_result,
    failed_result,
    parse_datetime,
    provider_limit,
    provider_timeout,
    success_or_no_results_result,
    text_matches_company,
)
from satellite_news.provider.interface import ProviderResult
from satellite_news.schema import Company, NewsProviderConfig, PipelineContext, SourceType


class RSSProvider:
    provider_id = "rss_provider"

    def __init__(self, client: ProviderHTTPClient | None = None) -> None:
        self.client = client or ProviderHTTPClient()
        self._feed_cache: dict[str, str] = {}

    def fetch_raw_articles(
        self,
        *,
        company: Company,
        provider: NewsProviderConfig,
        context: PipelineContext,
    ) -> ProviderResult:
        feeds = rss_feed_urls(company=company, provider=provider)
        if context.dry_run:
            return dry_run_result(
                provider=provider,
                company=company,
                metadata={"feed_count": len(feeds), "feeds": feeds},
            )
        if not feeds:
            return success_or_no_results_result(
                provider=provider,
                company=company,
                articles=[],
                metadata={"feed_count": 0, "reason": "No RSS feed URLs configured."},
            )

        articles = []
        warnings: list[str] = []
        cache_hit_count = 0
        network_feed_count = 0
        timeout = provider_timeout(provider)
        limit = provider_limit(provider)
        adapter_options = provider.options.get("adapter_options", {})
        per_feed_limit = int(
            adapter_options.get("max_items_per_feed", 8)
            if isinstance(adapter_options, dict)
            else 8
        )
        for feed_url in feeds:
            feed_article_count = 0
            try:
                if feed_url in self._feed_cache:
                    text = self._feed_cache[feed_url]
                    cache_hit_count += 1
                else:
                    text = self.client.get_text(feed_url, timeout_seconds=timeout)
                    self._feed_cache[feed_url] = text
                    network_feed_count += 1
                for row in parse_feed_items(text):
                    title = str(row.get("title") or "")
                    url = str(row.get("url") or "")
                    summary = str(row.get("summary") or "")
                    if not text_matches_company(
                        text=f"{title} {summary} {url}",
                        company=company,
                        provider=provider,
                    ):
                        continue
                    article = build_raw_article(
                        company=company,
                        provider=provider,
                        source_type=SourceType.RSS,
                        title=title,
                        url=url,
                        published_at=parse_datetime(row.get("published_at")),
                        raw_text=summary or None,
                        raw_payload={**row, "feed_url": feed_url},
                        metadata={
                            "feed_url": feed_url,
                            "source_name": row.get("publisher_name") or feed_hostname(feed_url),
                            "publisher_url": row.get("publisher_url"),
                        },
                    )
                    if article:
                        articles.append(article)
                        feed_article_count += 1
                    if feed_article_count >= per_feed_limit:
                        break
            except Exception as exc:  # pragma: no cover - exercised via provider tests
                warnings.append(f"{feed_url}: {type(exc).__name__}: {exc}")

        unique_articles = balanced_articles(articles=articles, feeds=feeds, limit=limit)

        if warnings and not articles:
            return failed_result(
                provider=provider,
                company=company,
                exc=RuntimeError("; ".join(warnings[:3])),
                metadata={"feed_count": len(feeds), "feeds": feeds},
            )
        return success_or_no_results_result(
            provider=provider,
            company=company,
            articles=unique_articles,
            warnings=tuple(warnings),
            metadata={
                "feed_count": len(feeds),
                "feeds": feeds,
                "warning_count": len(warnings),
                "per_feed_limit": per_feed_limit,
                "cache_hit_count": cache_hit_count,
                "network_feed_count": network_feed_count,
                "source_count": len(
                    {
                        str(article.metadata.get("source_name") or article.metadata.get("feed_url"))
                        for article in unique_articles
                    }
                ),
                "cache_status": "not_implemented",
                "stale_fallback_available": False,
            },
        )


def rss_feed_urls(*, company: Company, provider: NewsProviderConfig) -> tuple[str, ...]:
    values: list[str] = []
    override = company_override(company=company, provider=provider)
    if override:
        values.extend(url_values(override.options.get("feeds")))
        values.extend(url_values(override.options.get("feed_url")))
        values.extend(url_values(override.options.get("url")))
    values.extend(china_query_feed_urls(company=company, provider=provider))
    values.extend(url_values(provider.options.get("global_feeds")))
    values.extend(url_values(provider.options.get("feeds")))
    values.extend(url_values(provider.options.get("feed_url")))
    values.extend(url_values(provider.options.get("url")))
    seen = set()
    urls = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            urls.append(value)
    return tuple(urls)


def url_values(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        urls = []
        for row in value.values():
            urls.extend(url_values(row))
        return urls
    if isinstance(value, (list, tuple)):
        urls = []
        for row in value:
            urls.extend(url_values(row))
        return urls
    return []


def china_query_feed_urls(
    *,
    company: Company,
    provider: NewsProviderConfig,
) -> list[str]:
    if company.country_or_region.casefold() not in {"china", "cn", "中国", "中国大陆"}:
        return []
    templates = []
    for option_name in (
        "china_market_query_templates",
        "china_event_query_templates",
        "china_source_query_templates",
    ):
        templates.extend(url_values(provider.options.get(option_name)))
    feeds = []
    for template in templates:
        query = template.format(company_name=company.canonical_name)
        feeds.append(
            "https://news.google.com/rss/search?"
            + urlencode(
                {
                    "q": query,
                    "hl": "zh-CN",
                    "gl": "CN",
                    "ceid": "CN:zh-Hans",
                }
            )
        )
    return feeds


def parse_feed_items(text: str) -> list[dict[str, str]]:
    root = ET.fromstring(text)
    rows = []
    for item in root.findall(".//item"):
        rows.append(
            {
                "title": child_text(item, "title"),
                "url": child_text(item, "link") or child_text(item, "guid"),
                "summary": child_text(item, "description"),
                "published_at": child_text(item, "pubDate"),
                "publisher_name": child_text(item, "source"),
                "publisher_url": child_attribute(item, "source", "url"),
            }
        )
    for entry in root.findall(".//{http://www.w3.org/2005/Atom}entry"):
        rows.append(
            {
                "title": namespaced_text(entry, "title"),
                "url": atom_link(entry),
                "summary": namespaced_text(entry, "summary") or namespaced_text(entry, "content"),
                "published_at": namespaced_text(entry, "published") or namespaced_text(entry, "updated"),
            }
        )
    return rows


def child_text(element: ET.Element, tag: str) -> str:
    child = element.find(tag)
    return "" if child is None or child.text is None else child.text.strip()


def child_attribute(element: ET.Element, tag: str, attribute: str) -> str:
    child = element.find(tag)
    return "" if child is None else str(child.attrib.get(attribute) or "").strip()


def namespaced_text(element: ET.Element, tag: str) -> str:
    child = element.find(f"{{http://www.w3.org/2005/Atom}}{tag}")
    return "" if child is None or child.text is None else child.text.strip()


def atom_link(element: ET.Element) -> str:
    for link in element.findall("{http://www.w3.org/2005/Atom}link"):
        href = link.attrib.get("href")
        if href:
            return href.strip()
    return ""


def balanced_articles(*, articles, feeds: tuple[str, ...], limit: int):
    """Select one item per feed per round before taking a second from any feed."""
    by_feed = {feed: [] for feed in feeds}
    for article in articles:
        feed = str(article.metadata.get("feed_url") or "")
        by_feed.setdefault(feed, []).append(article)
    for rows in by_feed.values():
        rows.sort(
            key=lambda article: article.published_at.isoformat() if article.published_at else "",
            reverse=True,
        )

    selected = []
    seen_urls = set()
    row_index = 0
    while len(selected) < limit:
        added = False
        for feed in feeds:
            rows = by_feed.get(feed, [])
            if row_index >= len(rows):
                continue
            article = rows[row_index]
            if article.url not in seen_urls:
                seen_urls.add(article.url)
                selected.append(article)
                added = True
                if len(selected) >= limit:
                    break
        if not added and all(row_index >= len(rows) - 1 for rows in by_feed.values()):
            break
        row_index += 1
    return selected


def feed_hostname(url: str) -> str:
    return (urlsplit(url).hostname or "RSS").removeprefix("www.")
