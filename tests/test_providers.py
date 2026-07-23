from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

from satellite_news.config import load_companies, load_providers
from satellite_news.fetcher.gdelt import GDELTTransportError, GDELTFetcher
from satellite_news.pipeline import Pipeline
from satellite_news.provider import (
    BraveNewsProvider,
    GDELTProvider,
    NewsAPIProvider,
    NewsProviderRegistry,
    OfficialPageProvider,
    ProviderOrchestrator,
    RSSProvider,
    SerpApiGoogleNewsProvider,
    SpaceflightNewsAPIProvider,
)
from satellite_news.provider.interface import ProviderResult
from satellite_news.schema import (
    Company,
    NewsProviderConfig,
    PipelineContext,
    RawArticle,
    SourceType,
)


def test_rss_provider_filters_feed_items_to_raw_articles():
    class MockClient:
        def get_text(self, url, *, timeout_seconds=20, headers=None):
            assert url == "https://example.test/feed.xml"
            return """
            <rss><channel>
              <item>
                <title>SpaceX launches Starlink satellites</title>
                <link>https://example.test/spacex</link>
                <description>Starlink satellite launch update.</description>
                <pubDate>Mon, 15 Jun 2026 08:00:00 GMT</pubDate>
              </item>
              <item>
                <title>Unrelated market brief</title>
                <link>https://example.test/other</link>
              </item>
            </channel></rss>
            """

    company = company_by_id("spacex")
    provider = replace(
        provider_by_id("rss_provider"),
        options={"feeds": ["https://example.test/feed.xml"], "adapter_options": {"max_items": 5}},
    )
    context = PipelineContext(
        run_id="rss-test",
        started_at=datetime(2026, 6, 15, tzinfo=timezone.utc),
        dry_run=False,
    )

    result = RSSProvider(client=MockClient()).fetch_raw_articles(
        company=company,
        provider=provider,
        context=context,
    )

    assert result.status == "success"
    assert len(result.articles) == 1
    assert result.articles[0].source_type is SourceType.RSS
    assert result.articles[0].provider_id == "rss_provider"


def test_official_page_provider_extracts_matching_links_only():
    class MockClient:
        def get_text(self, url, *, timeout_seconds=20, headers=None):
            assert url == "https://www.spacex.com/updates/"
            return """
            <html>
              <head>
                <title>SpaceX Updates</title>
                <meta name="description" content="SpaceX company updates">
                <meta property="article:published_time" content="2026-06-15T08:00:00Z">
              </head>
              <body>
                <a href="/updates/starlink-launch">SpaceX Starlink mission update</a>
                <a href="/careers">Careers</a>
              </body>
            </html>
            """

    company = company_by_id("spacex")
    provider = provider_by_id("official_site_provider")
    context = PipelineContext(
        run_id="official-test",
        started_at=datetime(2026, 6, 15, tzinfo=timezone.utc),
        dry_run=False,
    )

    result = OfficialPageProvider(client=MockClient()).fetch_raw_articles(
        company=company,
        provider=provider,
        context=context,
    )

    assert result.status == "success"
    assert {article.source_type for article in result.articles} == {SourceType.OFFICIAL_SITE}
    assert any(article.url.endswith("/updates/starlink-launch") for article in result.articles)


def test_gdelt_provider_maps_429_to_rate_limited():
    class RateLimitedTransport:
        def search(self, request):
            raise GDELTTransportError("HTTP Error 429", rate_limited=True, retry_count=1)

    context = PipelineContext(
        run_id="gdelt-provider-rate-limit",
        started_at=datetime(2026, 6, 15, tzinfo=timezone.utc),
        dry_run=False,
    )

    result = GDELTProvider(fetcher=GDELTFetcher(transport=RateLimitedTransport())).fetch_raw_articles(
        company=company_by_id("spacex"),
        provider=provider_by_id("gdelt_provider"),
        context=context,
    )

    assert result.status == "rate_limited"
    assert result.should_fallback is True
    assert result.metadata["rate_limited"] is True
    assert result.metadata["retry_count"] == 1


def test_secret_providers_skip_without_api_keys(monkeypatch):
    monkeypatch.delenv("SERPAPI_KEY", raising=False)
    monkeypatch.delenv("NEWSAPI_KEY", raising=False)
    monkeypatch.delenv("BRAVE_SEARCH_API_KEY", raising=False)
    company = company_by_id("spacex")
    context = PipelineContext(
        run_id="secret-test",
        started_at=datetime(2026, 6, 15, tzinfo=timezone.utc),
        dry_run=False,
    )

    serp = SerpApiGoogleNewsProvider().fetch_raw_articles(
        company=company,
        provider=provider_by_id("serpapi_provider"),
        context=context,
    )
    newsapi = NewsAPIProvider().fetch_raw_articles(
        company=company,
        provider=provider_by_id("newsapi_provider"),
        context=context,
    )
    brave = BraveNewsProvider().fetch_raw_articles(
        company=company,
        provider=provider_by_id("brave_news_provider"),
        context=context,
    )

    assert serp.status == "skipped_no_secret"
    assert newsapi.status == "skipped_no_secret"
    assert brave.status == "skipped_no_secret"
    assert serp.should_fallback is True
    assert newsapi.should_fallback is True
    assert brave.should_fallback is True


def test_spaceflight_news_provider_maps_keyless_results():
    class MockClient:
        def get_json(self, url, *, timeout_seconds=20, headers=None):
            assert "spaceflightnewsapi.net" in url
            assert "search=SpaceX" in url
            return {
                "results": [
                    {
                        "title": "SpaceX launches Starlink satellites",
                        "url": "https://example.test/spaceflight-news",
                        "summary": "A Falcon 9 satellite launch update.",
                        "published_at": "2026-07-22T12:00:00Z",
                        "news_site": "Spaceflight Now",
                    }
                ]
            }

    result = SpaceflightNewsAPIProvider(client=MockClient()).fetch_raw_articles(
        company=company_by_id("spacex"),
        provider=provider_by_id("spaceflight_news_provider"),
        context=PipelineContext(
            run_id="spaceflight-news-test",
            started_at=datetime(2026, 7, 23, tzinfo=timezone.utc),
            dry_run=False,
        ),
    )

    assert result.status == "success"
    assert len(result.articles) == 1
    assert result.articles[0].metadata["source_name"] == "Spaceflight Now"


def test_brave_news_provider_maps_results_and_uses_secret(monkeypatch):
    monkeypatch.setenv("BRAVE_SEARCH_API_KEY", "test-brave-key")

    class MockClient:
        def get_json(self, url, *, timeout_seconds=20, headers=None):
            assert "api.search.brave.com" in url
            assert "q=%22SpaceX%22" in url
            assert headers["X-Subscription-Token"] == "test-brave-key"
            return {
                "results": [
                    {
                        "title": "SpaceX schedules another Starlink launch",
                        "url": "https://example.test/brave-news",
                        "description": "The mission will deploy broadband satellites.",
                        "page_age": "2026-07-22T12:00:00Z",
                        "profile": {"long_name": "Independent Space Desk"},
                    }
                ]
            }

    result = BraveNewsProvider(client=MockClient()).fetch_raw_articles(
        company=company_by_id("spacex"),
        provider=provider_by_id("brave_news_provider"),
        context=PipelineContext(
            run_id="brave-news-test",
            started_at=datetime(2026, 7, 23, tzinfo=timezone.utc),
            dry_run=False,
        ),
    )

    assert result.status == "success"
    assert len(result.articles) == 1
    assert result.articles[0].metadata["source_name"] == "Independent Space Desk"


def test_rss_provider_balances_results_across_feeds():
    class MockClient:
        def get_text(self, url, *, timeout_seconds=20, headers=None):
            source = "Alpha" if url.endswith("alpha.xml") else "Beta"
            return f"""
            <rss><channel>
              <item>
                <title>SpaceX Starlink satellite update from {source}</title>
                <link>https://example.test/{source.lower()}</link>
                <source url="https://{source.lower()}.test">{source} News</source>
                <pubDate>Wed, 22 Jul 2026 08:00:00 GMT</pubDate>
              </item>
              <item>
                <title>SpaceX Starlink second update from {source}</title>
                <link>https://example.test/{source.lower()}-second</link>
              </item>
            </channel></rss>
            """

    provider = replace(
        provider_by_id("rss_provider"),
        options={
            "feeds": ["https://feed.test/alpha.xml", "https://feed.test/beta.xml"],
            "adapter_options": {"max_items": 10, "max_items_per_feed": 1},
        },
    )
    result = RSSProvider(client=MockClient()).fetch_raw_articles(
        company=company_by_id("spacex"),
        provider=provider,
        context=PipelineContext(
            run_id="balanced-rss-test",
            started_at=datetime(2026, 7, 23, tzinfo=timezone.utc),
            dry_run=False,
        ),
    )

    assert len(result.articles) == 2
    assert {article.metadata["source_name"] for article in result.articles} == {
        "Alpha News",
        "Beta News",
    }
    assert result.metadata["source_count"] == 2


def test_provider_orchestrator_records_failure_and_continues_to_fallback():
    company = Company(id="spacex", canonical_name="SpaceX")
    providers = (
        NewsProviderConfig(id="rss_provider", type=SourceType.RSS, rank_group="media", priority=10),
        NewsProviderConfig(id="gdelt_provider", type=SourceType.GDELT, rank_group="wire", priority=30),
        NewsProviderConfig(id="serpapi_provider", type=SourceType.SERPAPI, rank_group="search", priority=40),
    )

    class EmptyRSS:
        provider_id = "rss_provider"

        def fetch_raw_articles(self, *, company, provider, context):
            return ProviderResult(
                provider_id=provider.id,
                company_id=company.id,
                status="no_results",
                should_fallback=True,
            )

    class RateLimitedGDELT:
        provider_id = "gdelt_provider"

        def fetch_raw_articles(self, *, company, provider, context):
            return ProviderResult(
                provider_id=provider.id,
                company_id=company.id,
                status="rate_limited",
                should_fallback=True,
                metadata={"rate_limited": True, "retry_count": 1},
            )

    class SuccessfulSerp:
        provider_id = "serpapi_provider"

        def fetch_raw_articles(self, *, company, provider, context):
            return ProviderResult(
                provider_id=provider.id,
                company_id=company.id,
                status="success",
                articles=(
                    RawArticle(
                        id="article-1",
                        company_id=company.id,
                        company_name=company.canonical_name,
                        source_id=provider.id,
                        source_type=SourceType.SERPAPI,
                        title="SpaceX Starlink news",
                        url="https://example.test/spacex",
                        provider_id=provider.id,
                        provider_priority=provider.priority,
                    ),
                ),
            )

    context = PipelineContext(
        run_id="fallback-test",
        started_at=datetime(2026, 6, 15, tzinfo=timezone.utc),
        dry_run=False,
    )
    result = Pipeline(
        provider_orchestrator=ProviderOrchestrator(
            registry=NewsProviderRegistry((EmptyRSS(), RateLimitedGDELT(), SuccessfulSerp())),
            providers=providers,
        )
    ).run(companies=(company,), providers=providers, context=context)

    assert len(result.items) == 1
    assert [row["provider_id"] for row in result.fetch_statuses] == [
        "rss_provider",
        "gdelt_provider",
        "serpapi_provider",
    ]
    assert result.fetch_statuses[1]["status"] == "rate_limited"
    assert result.fetch_statuses[2]["status"] == "success"


def company_by_id(company_id: str):
    return next(company for company in load_companies(Path("config/companies.yaml")) if company.id == company_id)


def provider_by_id(provider_id: str):
    return next(
        provider for provider in load_providers(Path("config/sources.yaml")) if provider.id == provider_id
    )
