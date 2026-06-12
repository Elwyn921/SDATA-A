import json
import urllib.error
import zipfile
from pathlib import Path

import pytest

import src.news_pipeline as news_pipeline


FIXTURE_RSS = Path("tests/fixtures/rss.xml").read_bytes()


class FakeHTTPClient:
    def __init__(self, *, json_payload=None, bytes_payload=b""):
        self.json_payload = json_payload or {}
        self.bytes_payload = bytes_payload
        self.requests = []

    def request_json(self, url, params=None, headers=None, timeout=None):
        self.requests.append(("json", url, params or {}))
        return self.json_payload

    def request_bytes(self, url, params=None, headers=None, timeout=None):
        self.requests.append(("bytes", url, params or {}))
        return self.bytes_payload


def write_config(path: Path, *, required_env=None, sources=None) -> Path:
    config = {
        "pipeline": {
            "name": "test-pipeline",
            "max_items": 10,
            "required_env": required_env or [],
        },
        "topics": [
            {
                "id": "ai",
                "label": "AI",
                "keywords": ["ai", "machine learning", "agent"],
            },
            {
                "id": "supply_chain",
                "label": "Supply Chain",
                "keywords": ["supply chain", "shipping", "logistics", "manufacturing"],
            },
        ],
        "sources": sources
        or [
            {
                "id": "fixture",
                "name": "Fixture Feed",
                "type": "rss",
                "url": "https://example.test/feed.xml",
                "trust_tier": 1,
                "enabled": True,
            }
        ],
    }
    path.write_text(json.dumps(config), encoding="utf-8")
    return path


def test_fixture_run_writes_report_summary_items_and_log(tmp_path):
    out_dir = tmp_path / "out"

    exit_code = news_pipeline.main(
        [
            "--config",
            "config/news_sources.json",
            "--fixture",
            "tests/fixtures/rss.xml",
            "--out",
            str(out_dir),
            "--max-items",
            "3",
        ]
    )

    assert exit_code == 0
    for filename in (
        "report.md",
        "weekly-report.md",
        "items.jsonl",
        "summary.json",
        "llm-input.json",
        "news-report.xlsx",
        "pages/index.html",
        "pipeline.log",
    ):
        assert (out_dir / filename).is_file()

    report = (out_dir / "report.md").read_text(encoding="utf-8")
    assert "News Intelligence Brief" in report
    assert "AI agents reshape supply chain logistics" in report

    rows = [
        json.loads(line)
        for line in (out_dir / "items.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert len(rows) == 2
    assert rows[0]["priority"] == "high"
    assert rows[0]["importance_score"] >= 70
    assert rows[0]["event_category"] == "supply_chain_operations"
    assert rows[0]["schema_version"] == news_pipeline.RAW_ARTICLE_SCHEMA_VERSION
    assert "ai" in rows[0]["topics"]
    assert "supply_chain" in rows[0]["topics"]

    weekly_report = (out_dir / "weekly-report.md").read_text(encoding="utf-8")
    assert "Weekly News Report" in weekly_report
    assert "Recommended action" in weekly_report

    pages_index = (out_dir / "pages/index.html").read_text(encoding="utf-8")
    assert "SDATA A News Intelligence" in pages_index
    assert "AI agents reshape supply chain logistics" in pages_index

    llm_input = json.loads((out_dir / "llm-input.json").read_text(encoding="utf-8"))
    assert llm_input["items"][0]["id"] == rows[0]["id"]

    with zipfile.ZipFile(out_dir / "news-report.xlsx") as workbook:
        sheet_xml = workbook.read("xl/worksheets/sheet1.xml").decode("utf-8")
    assert "Why It Matters" in sheet_xml
    assert "AI agents reshape supply chain logistics" in sheet_xml

    summary = json.loads((out_dir / "summary.json").read_text(encoding="utf-8"))
    assert summary["items"] == 2
    assert "news-report.xlsx" in summary["output_files"]
    assert "pages/index.html" in summary["output_files"]
    assert summary["source_errors"] == []
    assert "Wrote outputs" in (out_dir / "pipeline.log").read_text(encoding="utf-8")


def test_collect_uses_mocked_api_responses_and_records_source_errors():
    config = {
        "sources": [
            {"id": "good", "name": "Good Feed", "url": "https://example.test/good.xml"},
            {"id": "bad", "name": "Bad Feed", "url": "https://example.test/bad.xml"},
        ]
    }

    class FakeHTTPClient:
        def request_bytes(self, url, **_kwargs):
            if url.endswith("bad.xml"):
                raise urllib.error.URLError("temporary DNS failure")
            return FIXTURE_RSS

    items, errors = news_pipeline.collect(config, http_client=FakeHTTPClient())

    assert len(items) == 2
    assert len(errors) == 1
    assert errors[0]["source_id"] == "bad"
    assert errors[0]["source_type"] == "rss"
    assert "temporary DNS failure" in errors[0]["error"]


def test_gdelt_fetcher_maps_articles_to_raw_schema():
    source = {
        "id": "gdelt",
        "name": "GDELT",
        "type": "gdelt",
        "query": "AI supply chain",
        "trust_tier": 3,
    }
    http = FakeHTTPClient(
        json_payload={
            "articles": [
                {
                    "title": "AI reshapes global logistics",
                    "url": "https://example.test/story#section",
                    "seendate": "20260612083000",
                    "language": "English",
                    "sourceCountry": "US",
                    "domain": "example.test",
                    "socialimage": "https://example.test/image.jpg",
                }
            ]
        }
    )

    rows = news_pipeline.fetch_gdelt(source, http)

    assert len(rows) == 1
    assert rows[0]["schema_version"] == news_pipeline.RAW_ARTICLE_SCHEMA_VERSION
    assert rows[0]["fetcher"] == "gdelt"
    assert rows[0]["url"] == "https://example.test/story"
    assert rows[0]["published_at"] == "2026-06-12T08:30:00+00:00"
    assert rows[0]["metadata"]["domain"] == "example.test"
    assert http.requests[0][2]["query"] == "AI supply chain"


def test_newsapi_and_serpapi_fetchers_use_env_keys(monkeypatch):
    monkeypatch.setenv("NEWSAPI_KEY", "news-key")
    monkeypatch.setenv("SERPAPI_KEY", "serp-key")

    newsapi_source = {
        "id": "newsapi",
        "name": "NewsAPI",
        "type": "newsapi",
        "query": "AI",
    }
    newsapi_http = FakeHTTPClient(
        json_payload={
            "status": "ok",
            "articles": [
                {
                    "source": {"id": "wired", "name": "Wired"},
                    "author": "Reporter",
                    "title": "AI agent deployment expands",
                    "description": "Enterprise rollout",
                    "url": "https://example.test/newsapi",
                    "publishedAt": "2026-06-12T09:00:00Z",
                }
            ],
        }
    )
    serpapi_source = {
        "id": "serpapi",
        "name": "SerpApi",
        "type": "serpapi",
        "query": "AI logistics",
    }
    serpapi_http = FakeHTTPClient(
        json_payload={
            "news_results": [
                {
                    "title": "Supply chain AI update",
                    "link": "https://example.test/serpapi",
                    "snippet": "A new deployment",
                    "date": "2 hours ago",
                    "source": {"name": "Example News"},
                }
            ]
        }
    )

    newsapi_rows = news_pipeline.fetch_newsapi(newsapi_source, newsapi_http)
    serpapi_rows = news_pipeline.fetch_serpapi(serpapi_source, serpapi_http)

    assert newsapi_rows[0]["raw_source"] == "newsapi"
    assert newsapi_rows[0]["metadata"]["publisher"] == "Wired"
    assert newsapi_http.requests[0][2]["apiKey"] == "news-key"
    assert serpapi_rows[0]["raw_source"] == "serpapi"
    assert serpapi_rows[0]["metadata"]["publisher"] == "Example News"
    assert serpapi_http.requests[0][2]["api_key"] == "serp-key"


def test_official_website_fetcher_extracts_filtered_same_domain_links():
    html = b"""
    <html>
      <head><meta name="description" content="Official updates"></head>
      <body>
        <a href="/news/ai-launch">AI launch details</a>
        <a href="https://elsewhere.test/news/ignore">Ignore external</a>
        <a href="/careers">Ignore careers</a>
      </body>
    </html>
    """
    source = {
        "id": "official",
        "name": "Official",
        "type": "official_website",
        "url": "https://example.test/news/",
        "include_patterns": ["/news/"],
        "same_domain": True,
    }

    rows = news_pipeline.fetch_official_website(source, FakeHTTPClient(bytes_payload=html))

    assert len(rows) == 1
    assert rows[0]["title"] == "AI launch details"
    assert rows[0]["url"] == "https://example.test/news/ai-launch"
    assert rows[0]["summary"] == "Official updates"
    assert rows[0]["schema_version"] == news_pipeline.RAW_ARTICLE_SCHEMA_VERSION


def test_rate_limiter_sleeps_until_minimum_interval_passes():
    now = [100.0]
    sleeps = []

    def fake_sleep(seconds):
        sleeps.append(seconds)
        now[0] += seconds

    limiter = news_pipeline.RateLimiter(1.0, sleeper=fake_sleep, clock=lambda: now[0])
    limiter.wait()
    now[0] += 0.25
    limiter.wait()

    assert sleeps == [0.75]


def test_http_client_retries_retryable_api_response():
    calls = []

    class FakeResponse:
        def read(self):
            return b'{"ok": true}'

        def close(self):
            pass

    def fake_opener(request, timeout):
        calls.append((request.full_url, timeout))
        if len(calls) == 1:
            raise urllib.error.HTTPError(
                request.full_url,
                503,
                "Service Unavailable",
                {"Retry-After": "0"},
                None,
            )
        return FakeResponse()

    client = news_pipeline.HTTPClient(retries=1, sleeper=lambda _: None, opener=fake_opener)

    assert client.request_json("https://api.example.test/search", {"q": "ai"}) == {"ok": True}
    assert len(calls) == 2
    assert calls[0][0].endswith("?q=ai")


def test_main_fails_fast_when_required_secret_is_missing(tmp_path, monkeypatch):
    config_path = write_config(tmp_path / "config.json", required_env=["NEWS_API_KEY"])
    out_dir = tmp_path / "out"
    monkeypatch.delenv("NEWS_API_KEY", raising=False)

    exit_code = news_pipeline.main(
        [
            "--config",
            str(config_path),
            "--fixture",
            "tests/fixtures/rss.xml",
            "--out",
            str(out_dir),
        ]
    )

    assert exit_code == 2
    assert not (out_dir / "report.md").exists()
    assert "Missing required environment variable" in (out_dir / "pipeline.log").read_text(
        encoding="utf-8"
    )


def test_main_fails_fast_when_enabled_api_source_secret_is_missing(tmp_path, monkeypatch):
    config_path = write_config(
        tmp_path / "config.json",
        sources=[
            {
                "id": "newsapi",
                "name": "NewsAPI",
                "type": "newsapi",
                "url": "https://newsapi.example.test",
                "query": "ai",
                "api_key_env": "NEWSAPI_KEY",
                "enabled": True,
            }
        ],
    )
    out_dir = tmp_path / "out"
    monkeypatch.delenv("NEWSAPI_KEY", raising=False)

    exit_code = news_pipeline.main(["--config", str(config_path), "--out", str(out_dir)])

    assert exit_code == 2
    assert "NEWSAPI_KEY" in (out_dir / "pipeline.log").read_text(encoding="utf-8")


def test_main_reports_bad_config_without_traceback(tmp_path):
    config_path = tmp_path / "bad.json"
    config_path.write_text(json.dumps({"pipeline": {"name": "bad"}}), encoding="utf-8")
    out_dir = tmp_path / "out"

    exit_code = news_pipeline.main(["--config", str(config_path), "--out", str(out_dir)])

    assert exit_code == 2
    assert "Config must define a sources list" in (out_dir / "pipeline.log").read_text(
        encoding="utf-8"
    )


def test_github_actions_workflow_is_configured_for_pytest_and_artifacts():
    workflow = Path(".github/workflows/news-intelligence.yml").read_text(encoding="utf-8")

    assert "actions/setup-python@v5" in workflow
    assert "python -m pip install -r requirements-dev.txt" in workflow
    assert "python -m pytest" in workflow
    assert "actions/upload-artifact@v4" in workflow
    assert "data/news/latest/" in workflow
