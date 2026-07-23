import ast
import socket
from datetime import datetime, timezone
from pathlib import Path

import pytest


def test_public_imports():
    from satellite_news import (
        NewsItem,
        NewsProviderConfig,
        NewsSummary,
        Pipeline,
        PipelineResult,
        PipelineStageError,
        RawArticle,
        SourceRecord,
    )
    from satellite_news.exporter import NewsExporter, NullExporter
    from satellite_news.fetcher import NullFetcher, SourceFetcher
    from satellite_news.llm import NewsSummarizer, NullSummarizer
    from satellite_news.processing import NewsProcessor, NullProcessor
    from satellite_news.provider import NewsProvider, NewsProviderRegistry, NullNewsProvider
    from satellite_news.storage import NullStorage, PipelineStorage

    assert Pipeline
    assert PipelineStageError
    assert NewsItem
    assert RawArticle
    assert NewsSummary
    assert PipelineResult
    assert SourceRecord
    assert NewsProviderConfig
    assert NewsProvider
    assert NewsProviderRegistry
    assert NullNewsProvider
    assert SourceFetcher
    assert NullFetcher
    assert NewsProcessor
    assert NullProcessor
    assert NewsSummarizer
    assert NullSummarizer
    assert NewsExporter
    assert NullExporter
    assert PipelineStorage
    assert NullStorage


def test_schema_contracts_are_importable_and_instantiable():
    from satellite_news.schema import (
        SCHEMA_VERSION,
        Company,
        NewsProviderConfig,
        NewsItem,
        PipelineContext,
        ProviderFallbackPolicy,
        SourceConfig,
        SourceRecord,
        SourceType,
    )

    source = SourceRecord(
        source_id="rss-main",
        source_type=SourceType.RSS,
        source_name="Example RSS",
        rank_group="official",
        url="https://example.invalid/feed.xml",
    )
    item = NewsItem(
        id="item-1",
        company_id="spacex",
        company_name="SpaceX",
        title="Placeholder title",
        url="https://example.invalid/news",
        source=source,
    )
    context = PipelineContext(run_id="test-run", started_at=datetime.now(timezone.utc))
    company = Company(id="spacex", canonical_name="SpaceX")
    config = SourceConfig(
        id="rss-main",
        type=SourceType.RSS,
        rank_group="official",
        provider_id="rss_provider",
        provider_priority=30,
        fallback_to=("serpapi_provider",),
    )
    provider = NewsProviderConfig(
        id="rss_provider",
        type=SourceType.RSS,
        rank_group="media",
        priority=30,
        fallback=ProviderFallbackPolicy(
            mode="on_empty_or_error",
            fallback_to=("serpapi_provider",),
        ),
    )

    assert SCHEMA_VERSION == "satellite_news.v1"
    assert item.source is source
    assert context.dry_run is True
    assert company.enabled is True
    assert config.enabled is True
    assert config.fallback_to == ("serpapi_provider",)
    assert provider.fallback.fallback_to == ("serpapi_provider",)


def test_provider_config_contracts_load_from_sources_yaml():
    from satellite_news.config import load_providers
    from satellite_news.schema import SourceType

    providers = load_providers(Path("config/sources.yaml"))
    provider_ids = {provider.id for provider in providers}

    assert provider_ids >= {
        "brave_news_provider",
        "official_site_provider",
        "gdelt_provider",
        "rss_provider",
        "serpapi_provider",
        "newsapi_provider",
        "spaceflight_news_provider",
    }
    assert [provider.priority for provider in providers] == sorted(
        provider.priority for provider in providers
    )
    assert [provider.id for provider in providers[:7]] == [
        "rss_provider",
        "official_site_provider",
        "spaceflight_news_provider",
        "gdelt_provider",
        "serpapi_provider",
        "brave_news_provider",
        "newsapi_provider",
    ]

    gdelt = next(provider for provider in providers if provider.id == "gdelt_provider")
    assert gdelt.type is SourceType.GDELT
    assert gdelt.fallback.fallback_to == ("serpapi_provider",)
    assert "spacex" in gdelt.company_overrides
    assert gdelt.company_overrides["spacex"].query_templates

    serpapi = next(provider for provider in providers if provider.id == "serpapi_provider")
    newsapi = next(provider for provider in providers if provider.id == "newsapi_provider")
    rss = next(provider for provider in providers if provider.id == "rss_provider")
    assert len(rss.options["global_feeds"]) == 9
    assert serpapi.type is SourceType.SERPAPI
    assert newsapi.type is SourceType.NEWSAPI
    assert next(
        provider for provider in providers if provider.id == "spaceflight_news_provider"
    ).type is SourceType.SEARCH_API
    assert next(
        provider for provider in providers if provider.id == "brave_news_provider"
    ).type is SourceType.SEARCH_API


def test_default_pipeline_dry_run_does_not_touch_network_or_llm(monkeypatch, tmp_path):
    from satellite_news.pipeline import main

    def fail_socket(*_args, **_kwargs):
        raise AssertionError("dry-run pipeline must not open network sockets")

    monkeypatch.setattr(socket, "socket", fail_socket)

    result = main(
        (
            "--output-dir",
            str(tmp_path / "latest"),
            "--publish-dir",
            str(tmp_path / "docs-data"),
        )
    )

    assert result.items == ()
    assert result.summaries == ()
    assert result.exports == ()


def test_pipeline_partial_run_cli_records_distributed_schedule_metadata(monkeypatch, tmp_path):
    from satellite_news.pipeline import main

    def fail_socket(*_args, **_kwargs):
        raise AssertionError("dry-run partial pipeline must not open network sockets")

    monkeypatch.setattr(socket, "socket", fail_socket)

    result = main(
        (
            "--company-id",
            "spacex",
            "--provider-id",
            "gdelt_provider",
            "--scheduled-slot",
            "slot-2026-06-17T00-spacex-gdelt",
            "--max-gdelt-queries",
            "1",
            "--output-dir",
            str(tmp_path / "latest"),
            "--publish-dir",
            str(tmp_path / "docs-data"),
        )
    )

    assert {row["company_id"] for row in result.fetch_statuses} == {"spacex"}
    assert {row["provider_id"] for row in result.fetch_statuses} == {"gdelt_provider"}
    assert len(result.fetch_statuses) == 1
    status = result.fetch_statuses[0]
    assert status["partial_run"] is True
    assert status["scheduled_slot"] == "slot-2026-06-17T00-spacex-gdelt"
    assert status["scheduled_company_id"] == "spacex"
    assert status["scheduled_provider_id"] == "gdelt_provider"
    assert status["max_gdelt_queries"] == 1
    assert status["query_count"] == 1
    assert status["merge_policy"] == "A5_stale_latest_merge"


def test_source_tree_has_no_llm_provider_or_non_gdelt_network_imports():
    forbidden_roots = {
        "anthropic",
        "boto3",
        "google",
        "httpx",
        "openai",
        "requests",
        "socket",
    }
    imported_roots = set()

    for path in Path("src/satellite_news").rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported_roots.update(alias.name.split(".", 1)[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported_roots.add(node.module.split(".", 1)[0])

    assert imported_roots.isdisjoint(forbidden_roots)


def test_pipeline_error_boundary_logs_stage_failure(caplog):
    from satellite_news.pipeline import Pipeline, PipelineStageError
    from satellite_news.schema import PipelineStage

    class ExplodingProcessor:
        def process(self, *, items, context):
            raise RuntimeError("processor unavailable")

    with caplog.at_level("ERROR", logger="satellite_news.pipeline"):
        with pytest.raises(PipelineStageError) as excinfo:
            Pipeline(processor=ExplodingProcessor()).run()

    assert excinfo.value.stage == PipelineStage.PROCESS
    assert "Pipeline stage failed: process" in caplog.text


def test_github_actions_refreshes_pages_data_on_safe_schedule():
    workflow = Path(".github/workflows/news-intelligence.yml").read_text(encoding="utf-8")

    assert 'cron: "0 */6 * * *"' in workflow
    assert 'cron: "0 */3 * * *"' not in workflow
    assert 'cron: "15,45 * * * *"' not in workflow
    assert "permissions:\n  contents: write" in workflow
    assert "concurrency:\n  group: news-data-writer" in workflow
    assert "company_id:" in workflow
    assert "provider_id:" in workflow
    assert "scheduled_slot:" in workflow
    assert "max_gdelt_queries:" in workflow
    assert "python -m pip install --upgrade pip setuptools wheel" in workflow
    assert "python -m compileall -q src tests" in workflow
    assert "python -m pytest" in workflow
    assert "PYTHONPATH=src python3 -m satellite_news" in workflow
    assert "--no-dry-run" in workflow
    assert "--output-dir data/news/latest" in workflow
    assert "--publish-dir docs/data/news" in workflow
    assert 'elif [ "${{ github.event.schedule }}" = "0 */6 * * *" ]; then' in workflow
    assert "EXTRA_ARGS+=(--provider-id rss_provider)" in workflow
    assert "EXTRA_ARGS+=(--provider-id spaceflight_news_provider)" in workflow
    assert 'cron: "30 2 * * 1"' in workflow
    assert "EXTRA_ARGS+=(--provider-id brave_news_provider)" in workflow
    assert "--provider-id gdelt_provider" not in workflow
    assert "--max-gdelt-queries 1" not in workflow
    assert "SERPAPI_KEY: ${{ secrets.SERPAPI_KEY }}" in workflow
    assert "BRAVE_SEARCH_API_KEY: ${{ secrets.BRAVE_SEARCH_API_KEY }}" in workflow
    assert "NEWSAPI_KEY: ${{ secrets.NEWSAPI_KEY }}" in workflow
    assert "git add data/news docs/data/news" in workflow
    assert "git push" in workflow
    assert "upload-artifact" not in workflow
