"""Lightweight official-page provider adapter."""

from __future__ import annotations

from html.parser import HTMLParser
from typing import Any
from urllib.parse import urljoin

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


class OfficialPageProvider:
    provider_id = "official_site_provider"

    def __init__(self, client: ProviderHTTPClient | None = None) -> None:
        self.client = client or ProviderHTTPClient()

    def fetch_raw_articles(
        self,
        *,
        company: Company,
        provider: NewsProviderConfig,
        context: PipelineContext,
    ) -> ProviderResult:
        entrypoints = official_entrypoints(company=company, provider=provider)
        if context.dry_run:
            return dry_run_result(
                provider=provider,
                company=company,
                metadata={"entrypoint_count": len(entrypoints), "entrypoints": entrypoints},
            )
        if not entrypoints:
            return success_or_no_results_result(
                provider=provider,
                company=company,
                articles=[],
                metadata={"entrypoint_count": 0, "reason": "No official entrypoints configured."},
            )

        timeout = provider_timeout(provider)
        limit = provider_limit(provider, default=8)
        articles = []
        warnings: list[str] = []
        for entrypoint in entrypoints:
            try:
                html = self.client.get_text(entrypoint, timeout_seconds=timeout)
                page = OfficialPageParser()
                page.feed(html)
                page_text = f"{page.title} {page.description} {entrypoint}"
                if text_matches_company(text=page_text, company=company, provider=provider):
                    article = build_raw_article(
                        company=company,
                        provider=provider,
                        source_type=SourceType.OFFICIAL_SITE,
                        title=page.title or company.canonical_name,
                        url=entrypoint,
                        published_at=parse_datetime(page.published_at),
                        raw_text=page.description or None,
                        raw_payload={"entrypoint": entrypoint, "title": page.title},
                        metadata={"entrypoint": entrypoint, "official_page_kind": "entrypoint"},
                    )
                    if article:
                        articles.append(article)
                for link in page.links:
                    link_text = f"{link['text']} {link['href']}"
                    if not text_matches_company(text=link_text, company=company, provider=provider):
                        continue
                    article = build_raw_article(
                        company=company,
                        provider=provider,
                        source_type=SourceType.OFFICIAL_SITE,
                        title=link["text"] or page.title or company.canonical_name,
                        url=urljoin(entrypoint, link["href"]),
                        published_at=parse_datetime(page.published_at),
                        raw_payload={"entrypoint": entrypoint, "link": link},
                        metadata={"entrypoint": entrypoint, "official_page_kind": "link"},
                    )
                    if article:
                        articles.append(article)
                    if len(articles) >= limit:
                        break
            except Exception as exc:  # pragma: no cover - exercised via provider tests
                warnings.append(f"{entrypoint}: {type(exc).__name__}: {exc}")
            if len(articles) >= limit:
                break

        if warnings and not articles:
            return failed_result(
                provider=provider,
                company=company,
                exc=RuntimeError("; ".join(warnings[:3])),
                metadata={"entrypoint_count": len(entrypoints), "entrypoints": entrypoints},
            )
        return success_or_no_results_result(
            provider=provider,
            company=company,
            articles=dedupe_articles(articles),
            warnings=tuple(warnings),
            metadata={
                "entrypoint_count": len(entrypoints),
                "entrypoints": entrypoints,
                "warning_count": len(warnings),
                "cache_status": "not_implemented",
                "stale_fallback_available": False,
            },
        )


class OfficialPageParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title = ""
        self.description = ""
        self.published_at = ""
        self.links: list[dict[str, str]] = []
        self._in_title = False
        self._current_href = ""
        self._current_text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_map = {key.lower(): value or "" for key, value in attrs}
        if tag.lower() == "title":
            self._in_title = True
        elif tag.lower() == "meta":
            name = (attr_map.get("name") or attr_map.get("property") or "").lower()
            content = attr_map.get("content") or ""
            if name in {"description", "og:description", "twitter:description"} and content:
                self.description = self.description or content.strip()
            if name in {"article:published_time", "date", "pubdate", "publishdate"} and content:
                self.published_at = self.published_at or content.strip()
        elif tag.lower() == "a":
            self._current_href = attr_map.get("href") or ""
            self._current_text = []

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self.title += data
        if self._current_href:
            self._current_text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "title":
            self._in_title = False
            self.title = " ".join(self.title.split())
        elif tag.lower() == "a" and self._current_href:
            text = " ".join(" ".join(self._current_text).split())
            if text or self._current_href:
                self.links.append({"href": self._current_href, "text": text})
            self._current_href = ""
            self._current_text = []


def official_entrypoints(*, company: Company, provider: NewsProviderConfig) -> tuple[str, ...]:
    values: list[str] = []
    override = company_override(company=company, provider=provider)
    if override:
        values.extend(override.entrypoints)
        values.extend(url_values(override.options.get("entrypoints")))
        values.extend(url_values(override.options.get("url")))
    values.extend(url_values(provider.options.get("entrypoints")))
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
    if isinstance(value, (list, tuple)):
        values = []
        for row in value:
            values.extend(url_values(row))
        return values
    return []


def dedupe_articles(articles):
    seen = set()
    unique = []
    for article in articles:
        if article.url in seen:
            continue
        seen.add(article.url)
        unique.append(article)
    return unique
