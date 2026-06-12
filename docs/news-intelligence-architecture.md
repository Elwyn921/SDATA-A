# GitHub-Native News Intelligence Pipeline

This repository now treats GitHub as the control plane for a small news intelligence pipeline. The architecture is intentionally lightweight: configuration, execution, generated briefs, and audit history all live in the repo.

## Flow

1. GitHub Actions triggers the workflow on a six-hour schedule or manual dispatch.
2. `src/news_pipeline.py` reads `config/news_sources.json`.
3. Enabled sources are dispatched by `source.type`: RSS/Atom feeds, official websites, GDELT, NewsAPI, and SerpApi.
4. Fetchers normalize every result into `raw_article.v1`, then the pipeline deduplicates, topic-tags, and scores the shared item stream.
5. The Summary & Report Agent layer classifies event type, assigns 0-100 importance scores, and prepares report-ready summaries.
6. The pipeline writes machine-readable, analyst-facing, spreadsheet, and GitHub Pages-ready outputs to `data/news/latest/`.
7. GitHub stores the run artifact and optionally commits the latest brief back to the repository.

## Repository Contracts

- `config/news_sources.json` is the operator-controlled source and taxonomy registry.
- `src/news_pipeline.py` is the executable ingestion and scoring unit.
- `data/news/latest/items.jsonl` is the normalized item stream.
- `data/news/latest/summary.json` is the run summary for downstream automation.
- `data/news/latest/report.md` is the analyst-facing brief.
- `data/news/latest/weekly-report.md` is the weekly Markdown report.
- `data/news/latest/news-report.xlsx` is the spreadsheet handoff.
- `data/news/latest/llm-input.json` is the strict JSON input prepared for LLM enrichment.
- `data/news/latest/pages/index.html` is GitHub Pages-ready static content.
- `docs/llm-summary-report-agent-prompt.md` defines the strict JSON LLM output contract.
- `.github/workflows/news-intelligence.yml` is the GitHub-native orchestration layer.

## Fetcher Contract

Supported `source.type` values:

- `rss`, `atom`, `feed`: fetch XML, parse feed entries, and preserve feed metadata.
- `official_website`, `website`: fetch HTML, extract same-domain article links, and filter links with `include_patterns` and `exclude_patterns`.
- `gdelt`: query the GDELT 2.1 document API with `query`, `max_items`, optional `params`, and no API key.
- `newsapi`: query NewsAPI with `query`, optional `domains`, and an API key from `NEWSAPI_KEY` or source-level `api_key_env`.
- `serpapi`: query SerpApi Google News with `query`, optional `engine`, and an API key from `SERPAPI_KEY` or source-level `api_key_env`.

Every fetcher emits `raw_article.v1` with stable top-level fields: `id`, `schema_version`, `source_id`, `source_name`, `source_type`, `fetcher`, `trust_tier`, `title`, `url`, `summary`, `content`, `author`, `published_at`, `updated_at`, `collected_at`, `language`, `country`, `image_url`, `raw_source`, `raw`, and `metadata`.

HTTP behavior is centralized in `HTTPClient`: configurable timeout, retry count, exponential backoff, `Retry-After` support for retryable HTTP failures, and global request rate limiting.

## Extension Points

- Add or disable sources in `config/news_sources.json`.
- Add topics and keywords to steer intelligence scoring.
- Add downstream jobs after the collection step, such as opening issues for high-priority signals, publishing GitHub Pages, or posting to Slack.
- Replace deterministic report enrichment with an LLM enrichment step while keeping strict JSON output and the same generated report contracts.

## Local Commands

```bash
python3 -m pip install -r requirements-dev.txt
python3 -m pytest
python3 src/news_pipeline.py --config config/news_sources.json --fixture tests/fixtures/rss.xml --out data/news/latest --max-items 10
```
