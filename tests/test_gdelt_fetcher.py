from datetime import datetime, timezone
from pathlib import Path

from satellite_news.config import load_companies, load_sources
from satellite_news.fetcher.gdelt import GDELTHTTPTransport, GDELTFetcher, build_company_query
from satellite_news.pipeline import build_gdelt_fetcher
from satellite_news.pipeline import Pipeline
from satellite_news.schema import PipelineContext, SourceConfig, SourceType


def test_load_companies_and_sources_from_yaml():
    companies = load_companies(Path("config/companies.yaml"))
    sources = load_sources(Path("config/sources.yaml"))

    assert {company.id for company in companies} >= {"spacex", "blue_origin"}
    assert any(source.id == "gdelt_satellite_company_search" for source in sources)
    gdelt_source = next(
        source for source in sources if source.id == "gdelt_satellite_company_search"
    )
    assert gdelt_source.type is SourceType.GDELT
    assert gdelt_source.options["adapter_options"]["api_calls_allowed"] is True


def test_gdelt_query_uses_company_override_from_sources_yaml():
    company = next(
        company
        for company in load_companies(Path("config/companies.yaml"))
        if company.id == "spacex"
    )
    source = next(
        source
        for source in load_sources(Path("config/sources.yaml"))
        if source.id == "gdelt_satellite_company_search"
    )

    query = build_company_query(company=company, source=source)

    assert "SpaceX" in query
    assert "Starlink" in query
    assert "satellite" in query


def test_gdelt_query_falls_back_to_template_when_no_override():
    source = SourceConfig(
        id="gdelt",
        type=SourceType.GDELT,
        rank_group="wire",
        options={
            "query_template": (
                '("{company_name}" OR {company_alias_terms}) AND (satellite OR launch)'
            )
        },
    )
    company = next(
        company
        for company in load_companies(Path("config/companies.yaml"))
        if company.id == "blue_origin"
    )

    query = build_company_query(company=company, source=source)

    assert '"Blue Origin"' in query
    assert '"Blue Origin LLC"' in query
    assert "satellite OR launch" in query


def test_gdelt_dry_run_does_not_call_transport():
    class FailingTransport:
        def search(self, request):
            raise AssertionError("dry_run must not call transport")

    source = SourceConfig(
        id="gdelt",
        type=SourceType.GDELT,
        rank_group="wire",
        options={"adapter_options": {"api_calls_allowed": True}},
    )
    company = next(
        company
        for company in load_companies(Path("config/companies.yaml"))
        if company.id == "spacex"
    )
    context = PipelineContext(
        run_id="dry-run",
        started_at=datetime.now(timezone.utc),
        dry_run=True,
    )

    assert (
        GDELTFetcher(transport=FailingTransport()).fetch(
            company=company,
            source=source,
            context=context,
        )
        == ()
    )


def test_gdelt_mock_payload_maps_to_raw_article_and_news_item():
    class MockTransport:
        def __init__(self):
            self.requests = []

        def search(self, request):
            self.requests.append(request)
            return {
                "articles": [
                    {
                        "title": "SpaceX launches Starlink satellites",
                        "url": "https://example.test/spacex-starlink",
                        "seendate": "20260612083000",
                        "language": "English",
                        "domain": "example.test",
                        "sourceCountry": "US",
                        "snippet": "Launch campaign update.",
                    }
                ]
            }

    source = SourceConfig(
        id="gdelt",
        type=SourceType.GDELT,
        rank_group="wire_and_aggregator",
        description="GDELT test source",
        options={"adapter_options": {"api_calls_allowed": True}},
    )
    company = next(
        company
        for company in load_companies(Path("config/companies.yaml"))
        if company.id == "spacex"
    )
    context = PipelineContext(
        run_id="mock-run",
        started_at=datetime(2026, 6, 12, tzinfo=timezone.utc),
        dry_run=False,
    )
    transport = MockTransport()
    fetcher = GDELTFetcher(transport=transport)

    raw_articles = fetcher.fetch_raw_articles(company=company, source=source, context=context)
    items = fetcher.fetch(company=company, source=source, context=context)

    assert len(raw_articles) == 1
    assert raw_articles[0].company_id == "spacex"
    assert raw_articles[0].source_type is SourceType.GDELT
    assert raw_articles[0].published_at == datetime(2026, 6, 12, 8, 30, tzinfo=timezone.utc)
    assert raw_articles[0].metadata["gdelt_query"] == transport.requests[0].query
    assert len(items) == 1
    assert items[0].source.source_id == "gdelt"
    assert items[0].raw_text == "Launch campaign update."


def test_gdelt_http_transport_builds_request_with_params(monkeypatch):
    calls = []

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def read(self):
            return b'{"articles": []}'

    def fake_urlopen(request, timeout):
        calls.append((request.full_url, timeout, request.headers))
        return FakeResponse()

    monkeypatch.setattr("satellite_news.fetcher.gdelt.urllib.request.urlopen", fake_urlopen)
    request = next(
        source
        for source in load_sources(Path("config/sources.yaml"))
        if source.id == "gdelt_satellite_company_search"
    )
    company = next(
        company
        for company in load_companies(Path("config/companies.yaml"))
        if company.id == "spacex"
    )
    gdelt_request = GDELTFetcher().build_request(company=company, source=request)

    payload = GDELTHTTPTransport(timeout_seconds=7).search(gdelt_request)

    assert payload == {"articles": []}
    assert calls[0][1] == 7
    assert "api.gdeltproject.org/api/v2/doc/doc" in calls[0][0]
    assert "format=json" in calls[0][0]
    assert "maxrecords=5" in calls[0][0]


def test_gdelt_transport_failure_does_not_break_fetcher():
    class FailingTransport:
        def search(self, request):
            from satellite_news.fetcher.gdelt import GDELTTransportError

            raise GDELTTransportError("temporary GDELT rate limit")

    source = SourceConfig(
        id="gdelt",
        type=SourceType.GDELT,
        rank_group="wire",
        options={"adapter_options": {"api_calls_allowed": True}},
    )
    company = next(
        company
        for company in load_companies(Path("config/companies.yaml"))
        if company.id == "spacex"
    )
    context = PipelineContext(
        run_id="rate-limited",
        started_at=datetime.now(timezone.utc),
        dry_run=False,
    )

    assert GDELTFetcher(transport=FailingTransport()).fetch(
        company=company,
        source=source,
        context=context,
    ) == ()


def test_pipeline_builds_gdelt_fetcher_from_source_options():
    fetcher = build_gdelt_fetcher(load_sources(Path("config/sources.yaml")))

    assert isinstance(fetcher.transport, GDELTHTTPTransport)
    assert fetcher.transport.rate_limit_seconds == 30.0


def test_pipeline_maps_gdelt_results_for_all_four_companies_with_mock_transport():
    class FourCompanyTransport:
        def search(self, request):
            title_by_company = {
                "spacex": "SpaceX Starlink launch update",
                "blue_origin": "Blue Origin New Glenn update",
                "yuanxin_satellite": "SpaceSail Qianfan constellation update",
                "china_satnet": "China SatNet Guowang constellation update",
            }
            return {
                "articles": [
                    {
                        "title": title_by_company[request.company_id],
                        "url": f"https://example.test/{request.company_id}",
                        "seendate": "20260612083000",
                        "language": "English",
                    }
                ]
            }

    companies = load_companies(Path("config/companies.yaml"))
    sources = tuple(
        source
        for source in load_sources(Path("config/sources.yaml"))
        if source.type is SourceType.GDELT
    )
    context = PipelineContext(
        run_id="four-company-mock",
        started_at=datetime(2026, 6, 12, tzinfo=timezone.utc),
        dry_run=False,
    )

    result = Pipeline(fetcher=GDELTFetcher(transport=FourCompanyTransport())).run(
        companies=companies,
        sources=sources,
        context=context,
    )

    assert {item.company_id for item in result.items} == {
        "spacex",
        "blue_origin",
        "yuanxin_satellite",
        "china_satnet",
    }
    assert all(item.source.source_type is SourceType.GDELT for item in result.items)
