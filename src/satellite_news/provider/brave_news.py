"""Brave independent news-search provider."""

from __future__ import annotations

import os
import re
import time
import unicodedata
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from satellite_news.provider.base import (
    ProviderHTTPClient,
    build_raw_article,
    dry_run_result,
    failed_result,
    parse_datetime,
    provider_limit,
    provider_timeout,
    query_templates,
    skipped_no_secret_result,
    success_or_no_results_result,
    url_with_query,
)
from satellite_news.provider.interface import ProviderResult
from satellite_news.schema import Company, NewsProviderConfig, PipelineContext, SourceType


DEFAULT_ENDPOINT = "https://api.search.brave.com/res/v1/news/search"


class BraveNewsProvider:
    provider_id = "brave_news_provider"

    def __init__(self, client: ProviderHTTPClient | None = None) -> None:
        self.client = client or ProviderHTTPClient()
        self._last_request_at: float | None = None

    def fetch_raw_articles(
        self,
        *,
        company: Company,
        provider: NewsProviderConfig,
        context: PipelineContext,
    ) -> ProviderResult:
        adapter_options = provider.options.get("adapter_options", {})
        secret_env = str(
            adapter_options.get("api_key_env") or "BRAVE_SEARCH_API_KEY"
            if isinstance(adapter_options, dict)
            else "BRAVE_SEARCH_API_KEY"
        )
        api_key = os.getenv(secret_env)
        if not api_key:
            return skipped_no_secret_result(provider=provider, company=company, secret_env=secret_env)
        queries = query_templates(
            company=company,
            provider=provider,
            default_template='"{company_name}" satellite',
        )
        max_queries = int(adapter_options.get("max_queries_per_company") or 1)
        queries = queries[:max(1, max_queries)]
        if context.dry_run:
            return dry_run_result(
                provider=provider,
                company=company,
                metadata={"query_count": len(queries), "queries": queries},
            )

        endpoint = str(provider.options.get("endpoint") or DEFAULT_ENDPOINT)
        limit = provider_limit(provider)
        articles = []
        warnings = []
        successful_queries = 0
        for query in queries:
            try:
                self.wait_for_rate_limit(adapter_options)
                payload = self.client.get_json(
                    url_with_query(
                        endpoint,
                        {
                            "q": query,
                            "count": limit,
                            "freshness": str(adapter_options.get("freshness") or "pm"),
                            "country": str(adapter_options.get("country") or "CN"),
                            "search_lang": str(
                                adapter_options.get("search_lang") or "zh-hans"
                            ),
                            "ui_lang": str(adapter_options.get("ui_lang") or "zh-CN"),
                        },
                    ),
                    timeout_seconds=provider_timeout(provider),
                    headers={
                        "Accept": "application/json",
                        "X-Subscription-Token": api_key,
                    },
                )
                successful_queries += 1
                for row in payload.get("results", ()) or ():
                    if not isinstance(row, dict):
                        continue
                    profile = row.get("profile") if isinstance(row.get("profile"), dict) else {}
                    title = str(row.get("title") or "")
                    url = str(row.get("url") or "")
                    description = str(row.get("description") or "")
                    if not brave_result_matches_company(
                        text=f"{title} {description} {url}",
                        company=company,
                    ):
                        continue
                    article = build_raw_article(
                        company=company,
                        provider=provider,
                        source_type=SourceType.SEARCH_API,
                        title=title,
                        url=url,
                        published_at=parse_datetime(row.get("page_age")),
                        raw_text=description or None,
                        raw_payload=row,
                        metadata={
                            "brave_query": query,
                            "source_name": str(profile.get("long_name") or profile.get("url") or "Brave News"),
                        },
                    )
                    if article:
                        articles.append(article)
            except Exception as exc:  # pragma: no cover - network boundary
                warnings.append(f"{query}: {type(exc).__name__}: {exc}")

        if warnings and not articles:
            return failed_result(
                provider=provider,
                company=company,
                exc=RuntimeError("; ".join(warnings[:3])),
                metadata={"query_count": len(queries), "queries": queries},
            )
        return success_or_no_results_result(
            provider=provider,
            company=company,
            articles=tuple(dedupe_articles(articles)),
            warnings=tuple(warnings),
            metadata={
                "query_count": len(queries),
                "successful_query_count": successful_queries,
                "queries": queries,
                "warning_count": len(warnings),
                "quota_policy": {
                    "max_queries_per_company": max_queries,
                    "max_items_per_company": limit,
                    "rate_limit_seconds": float(
                        adapter_options.get("rate_limit_seconds") or 0
                    ),
                    "china_only": True,
                },
                "cache_status": "not_implemented",
                "stale_fallback_available": False,
            },
        )

    def wait_for_rate_limit(self, adapter_options) -> None:
        delay = float(adapter_options.get("rate_limit_seconds") or 0)
        if delay > 0 and self._last_request_at is not None:
            remaining = delay - (time.monotonic() - self._last_request_at)
            if remaining > 0:
                time.sleep(remaining)
        self._last_request_at = time.monotonic()


def dedupe_articles(articles):
    rows = []
    seen_urls = set()
    seen_titles = set()
    for article in articles:
        url_key = canonical_url_key(article.url)
        title_key = normalized_title_key(article.title)
        if (url_key and url_key in seen_urls) or (title_key and title_key in seen_titles):
            continue
        if url_key:
            seen_urls.add(url_key)
        if title_key:
            seen_titles.add(title_key)
        rows.append(article)
    return rows


def canonical_url_key(value: str) -> str:
    try:
        parsed = urlsplit(value.strip())
    except ValueError:
        return value.strip().casefold()
    host = (parsed.hostname or "").casefold().removeprefix("www.")
    query = urlencode(
        [
            (key, val)
            for key, val in parse_qsl(parsed.query, keep_blank_values=True)
            if not key.casefold().startswith("utm_")
            and key.casefold() not in {"ref", "source", "spm", "from", "share"}
        ]
    )
    return urlunsplit((parsed.scheme.casefold(), host, parsed.path.rstrip("/"), query, ""))


def normalized_title_key(value: str) -> str:
    text = unicodedata.normalize("NFKC", value).casefold()
    return re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "", text)


def brave_result_matches_company(*, text: str, company: Company) -> bool:
    haystack = " ".join(unicodedata.normalize("NFKC", text).casefold().split())
    identity_terms = [company.canonical_name, *company.aliases]
    return any(
        " ".join(unicodedata.normalize("NFKC", term).casefold().split()) in haystack
        for term in identity_terms
        if len(term.strip()) >= 3
    )
