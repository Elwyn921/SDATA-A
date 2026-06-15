import ast
import socket
from datetime import datetime, timezone
from pathlib import Path

import pytest


def test_public_imports():
    from satellite_news import (
        NewsItem,
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
    from satellite_news.storage import NullStorage, PipelineStorage

    assert Pipeline
    assert PipelineStageError
    assert NewsItem
    assert RawArticle
    assert NewsSummary
    assert PipelineResult
    assert SourceRecord
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
        NewsItem,
        PipelineContext,
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
    config = SourceConfig(id="rss-main", type=SourceType.RSS, rank_group="official")

    assert SCHEMA_VERSION == "satellite_news.v1"
    assert item.source is source
    assert context.dry_run is True
    assert company.enabled is True
    assert config.enabled is True


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


def test_github_actions_only_runs_static_and_import_checks():
    workflow = Path(".github/workflows/news-intelligence.yml").read_text(encoding="utf-8")

    assert "permissions:\n  contents: read" in workflow
    assert "python -m pip install --upgrade pip setuptools wheel" in workflow
    assert "python -m compileall -q src tests" in workflow
    assert "python -m pytest tests/test_imports.py tests/test_prompt_templates.py" in workflow
    assert "python -m satellite_news" not in workflow
    assert "git push" not in workflow
    assert "upload-artifact" not in workflow
