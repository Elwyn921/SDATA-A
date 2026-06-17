from datetime import datetime, timezone
from pathlib import Path

from satellite_news.config import load_companies, load_sources
from satellite_news.fetcher.gdelt import (
    GDELTHTTPTransport,
    GDELTTransportError,
    GDELTFetcher,
    build_company_query,
)
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


def test_gdelt_builds_multiple_queries_for_alias_rich_company():
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

    queries = GDELTFetcher().build_company_queries(company=company, source=source)

    assert len(queries) >= 2
    assert len({query.strip() for query in queries}) == len(queries)


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

    items = fetcher.fetch(company=company, source=source, context=context)

    assert len(items) >= 1
    assert items[0].source.source_id == "gdelt"
    assert items[0].raw_text == "Launch campaign update."
    assert items[0].metadata["gdelt_query"] == transport.requests[0].query


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

    assert payload["articles"] == []
    assert payload["_transport_meta"] == {"rate_limited": False, "retry_count": 0}
    assert calls[0][1] == 7
    assert "api.gdeltproject.org/api/v2/doc/doc" in calls[0][0]
    assert "format=json" in calls[0][0]
    assert "maxrecords=10" in calls[0][0]


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
    assert context.metadata["fetch_statuses"][0]["status"] == "failed"
    assert "temporary GDELT rate limit" in context.metadata["fetch_statuses"][0]["reason"]
    assert context.metadata["fetch_statuses"][0]["final_status"] == "failed"
    assert context.metadata["fetch_statuses"][0]["rate_limited"] is False


def test_gdelt_no_results_records_explicit_status():
    class EmptyTransport:
        def search(self, request):
            return {"articles": []}

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
        run_id="empty",
        started_at=datetime.now(timezone.utc),
        dry_run=False,
    )

    assert GDELTFetcher(transport=EmptyTransport()).fetch(
        company=company,
        source=source,
        context=context,
    ) == ()
    assert context.metadata["fetch_statuses"][0]["status"] == "no_results"
    assert context.metadata["fetch_statuses"][0]["final_status"] == "no_results"


def test_pipeline_builds_gdelt_fetcher_from_source_options():
    fetcher = build_gdelt_fetcher(load_sources(Path("config/sources.yaml")))

    assert isinstance(fetcher.transport, GDELTHTTPTransport)
    assert fetcher.transport.rate_limit_seconds == 25.0
    assert fetcher.transport.retries == 1
    assert fetcher.transport.backoff_seconds == 90.0


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
    assert {row["company_id"] for row in result.fetch_statuses} == {
        "spacex",
        "blue_origin",
        "yuanxin_satellite",
        "china_satnet",
    }
    assert {row["final_status"] for row in result.fetch_statuses} == {"success"}


def test_pipeline_collects_failed_and_successful_queries_without_breaking_company():
    class MixedTransport:
        def __init__(self):
            self.calls = []

        def search(self, request):
            self.calls.append(request.query)
            if "SpaceX" in request.query and "Starlink" in request.query:
                raise GDELTTransportError("boom")
            return {
                "articles": [
                    {
                        "title": f"Result for {request.company_id}",
                        "url": f"https://example.test/{request.company_id}/{len(self.calls)}",
                        "seendate": "20260612083000",
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
        run_id="mixed-queries",
        started_at=datetime(2026, 6, 12, tzinfo=timezone.utc),
        dry_run=False,
    )

    result = Pipeline(fetcher=GDELTFetcher(transport=MixedTransport())).run(
        companies=companies,
        sources=sources,
        context=context,
    )

    spacex_status = next(row for row in result.fetch_statuses if row["company_id"] == "spacex")
    assert spacex_status["final_status"] == "partial_success"
    assert spacex_status["failed_queries"] >= 1
    assert spacex_status["successful_query_count"] >= 1
    assert result.items


def test_rate_limited_queries_are_reported_as_rate_limited_when_no_items():
    class RateLimitedTransport:
        def search(self, request):
            raise GDELTTransportError("HTTP Error 429", rate_limited=True, retry_count=1)

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

    assert GDELTFetcher(transport=RateLimitedTransport()).fetch(
        company=company,
        source=source,
        context=context,
    ) == ()
    status = context.metadata["fetch_statuses"][0]
    assert status["final_status"] == "rate_limited"
    assert status["rate_limited"] is True
    assert status["retry_count"] >= 1
    assert status["error_message"]


def test_gdelt_max_queries_limits_distributed_partial_run():
    class CountingTransport:
        def __init__(self):
            self.calls = []

        def search(self, request):
            self.calls.append(request.query)
            return {
                "articles": [
                    {
                        "title": f"Result {len(self.calls)}",
                        "url": f"https://example.test/{len(self.calls)}",
                        "seendate": "20260612083000",
                    }
                ]
            }

    source = next(
        source
        for source in load_sources(Path("config/sources.yaml"))
        if source.id == "gdelt_satellite_company_search"
    )
    company = next(
        company
        for company in load_companies(Path("config/companies.yaml"))
        if company.id == "spacex"
    )
    context = PipelineContext(
        run_id="partial-gdelt",
        started_at=datetime.now(timezone.utc),
        dry_run=False,
        partial_run=True,
        scheduled_slot="slot-spacex-gdelt",
        company_id="spacex",
        provider_id="gdelt_provider",
        max_gdelt_queries=1,
        merge_policy="A5_stale_latest_merge",
        metadata={
            "partial_run": True,
            "scheduled_slot": "slot-spacex-gdelt",
            "company_id": "spacex",
            "provider_id": "gdelt_provider",
            "max_gdelt_queries": 1,
            "merge_policy": "A5_stale_latest_merge",
        },
    )
    transport = CountingTransport()

    items = GDELTFetcher(transport=transport).fetch(
        company=company,
        source=source,
        context=context,
    )

    assert len(transport.calls) == 1
    assert len(items) == 1
    status = context.metadata["fetch_statuses"][0]
    assert status["partial_run"] is True
    assert status["query_count"] == 1
    assert status["max_gdelt_queries"] == 1
    assert status["scheduled_slot"] == "slot-spacex-gdelt"
