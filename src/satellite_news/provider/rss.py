"""RSS provider adapter."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from typing import Any

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
        timeout = provider_timeout(provider)
        limit = provider_limit(provider)
        for feed_url in feeds:
            try:
                text = self.client.get_text(feed_url, timeout_seconds=timeout)
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
                        metadata={"feed_url": feed_url},
                    )
                    if article:
                        articles.append(article)
                    if len(articles) >= limit:
                        break
            except Exception as exc:  # pragma: no cover - exercised via provider tests
                warnings.append(f"{feed_url}: {type(exc).__name__}: {exc}")
            if len(articles) >= limit:
                break

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
            articles=dedupe_articles(articles),
            warnings=tuple(warnings),
            metadata={
                "feed_count": len(feeds),
                "feeds": feeds,
                "warning_count": len(warnings),
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


def namespaced_text(element: ET.Element, tag: str) -> str:
    child = element.find(f"{{http://www.w3.org/2005/Atom}}{tag}")
    return "" if child is None or child.text is None else child.text.strip()


def atom_link(element: ET.Element) -> str:
    for link in element.findall("{http://www.w3.org/2005/Atom}link"):
        href = link.attrib.get("href")
        if href:
            return href.strip()
    return ""


def dedupe_articles(articles):
    seen = set()
    unique = []
    for article in articles:
        if article.url in seen:
            continue
        seen.add(article.url)
        unique.append(article)
    return unique
