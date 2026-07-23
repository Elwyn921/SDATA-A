# SDATA A

SDATA A is a GitHub-native satellite news intelligence pipeline for monitoring satellite internet, launch, and space infrastructure companies. The project is now in a live RSS data-loop stage: it refreshes news data on GitHub Actions, writes JSON outputs, publishes frontend-readable data under `docs/`, and keeps archive records for later analysis.

The current goal is to make the public website stable first, then add LLM daily reports and deeper company intelligence.

## Current Status

Implemented:

- Live RSS news refresh for 13 monitored companies.
- GitHub Actions schedule that refreshes RSS data every 6 hours.
- Unified `PipelineResult`, `NewsItem`, `RawArticle`, and fetch-status contracts.
- JSON latest output under `data/news/latest/`.
- Historical archive output under `data/news/archive/`.
- De-duplicated long-lived news catalog under `data/news/archive/catalog.json`.
- Beijing-time daily news-count index under `data/news/latest/daily_index.json`.
- GitHub Pages data publication under `docs/data/news/`.
- Static GitHub Pages frontend under `docs/`.
- Observable dashboard prototype under `observable/`, built into `docs/observable/`.
- Partial-run CLI contracts for future provider/company-specific refreshes.
- Stale/latest merge behavior so partial updates can keep previously available company data.
- Scheduled A6 daily-report generator with OpenAI structured output and a readable no-secret fallback.
- Frontend daily briefing, 30-day news volume index, and date-based archive navigation.
- Deterministic quality gate for company relevance, satellite context, recency, canonical URLs, and near-duplicate removal.
- Balanced per-feed RSS collection so one aggregator cannot crowd out specialist and official sources.
- Keyless Spaceflight News API integration plus optional Brave News Search.

Currently paused or optional in production:

- GDELT scheduled production refresh. The adapter still exists, but frequent 429 rate limits make RSS the current production source.
- SerpApi, Brave News, and NewsAPI require API keys and run in a quota-controlled weekly search slot rather than the primary data loop.
- Excel, PDF, and Markdown report exports.
- Complex official-site crawling.

## Monitored Companies

Current monitoring covers 13 companies:

- Foreign major companies: SpaceX, Blue Origin
- Satellite internet services: 垣信卫星, 中国星网
- Satellite platform and spacecraft manufacturing: 银河航天, 蓝箭鸿擎 / 鸿擎科技, 微纳星空
- Launch vehicles and launch services: 蓝箭航天 / LandSpace, 中科宇航 / CAS Space, 天兵科技 / Space Pioneer, 星际荣耀 / i-Space, 星河动力 / Galactic Energy, 宇石空间

Latest local data snapshot:

- Latest run id: `08e76e21-26fb-4cb9-9362-f2906920b61b`
- Generated at: `2026-06-24T07:23:55.772959Z`
- Total news items: 591
- Provider used in latest snapshot: `rss_provider`
- Company coverage: all 13 companies have data

## Important Runtime Notes

RSS is the current stable production path. Some individual feeds may return 0 results or become unavailable, but provider failures are recorded per source/company and should not break the whole pipeline.

GDELT remains available as code, but it often returns `HTTP 429 Too Many Requests`. A 429 means the external public service is rate-limiting requests; it does not mean the SDATA A pipeline or frontend is broken. For now, GDELT should be treated as manual, low-frequency, or fallback infrastructure rather than the main scheduled source.

API-backed providers such as SerpApi, Brave News, and NewsAPI use environment variables / GitHub Secrets and gracefully skip when keys are missing.

## Project Structure

```text
config/
  companies.yaml          Company registry, aliases, keywords, and category metadata
  sources.yaml            Provider/source registry and per-company source configuration
  source_rank.yaml        Source ranking, quality, and dedupe policy
  prompt_templates.yaml   Prompt contracts for the future LLM reporting layer
data/
  news/latest/            Latest generated JSON outputs
  news/archive/           Historical run snapshots and durable news catalog
  reports/                Latest and date-archived daily briefings
docs/
  index.html              GitHub Pages frontend entry point
  assets/                 Static frontend JavaScript and styles
  data/news/latest/       Published JSON consumed by the frontend
  observable/             Built Observable dashboard output
observable/
  index.md                Observable Framework dashboard source
src/
  satellite_news/
    schema.py             Unified data structures
    config.py             YAML config loaders
    pipeline.py           Fetch -> process -> summarize -> export -> store orchestration
    provider/             NewsProvider contracts and provider adapters
    fetcher/              External fetch helpers, including GDELT transport
    processing/           Processing interface
    llm/                  LLM summarizer interface, currently no-op
    reporting/            Scheduled daily-report generator and archive writer
    exporter/             Export interface, currently no-op
    storage/json_file.py  JSON latest/archive storage and docs publication
tests/
  test_*.py               Import, provider, storage, and contract checks
```

## Data Flow

```text
config/companies.yaml + config/sources.yaml
        ->
NewsProvider adapters
        ->
RawArticle
        ->
NewsItem
        ->
PipelineResult
        ->
data/news/latest/*.json + data/news/archive/**
        ->
docs/data/news/latest/pipeline_result.json
        ->
GitHub Pages / Observable dashboard
```

## Provider Contract

Provider configuration lives in `config/sources.yaml`. Provider implementations must output unified `RawArticle` records so downstream processing can normalize them into `NewsItem`.

Current provider posture:

- `rss_provider`: production source, scheduled every 6 hours with per-feed balancing.
- `spaceflight_news_provider`: keyless specialist-space aggregation, scheduled with RSS.
- `official_site_provider`: available as a light official-page path, but not the main production source.
- `gdelt_provider`: implemented, currently paused from production schedule because of 429 rate limits.
- `serpapi_provider`: Google News search coverage, enabled by `SERPAPI_KEY` in the weekly premium-search slot.
- `brave_news_provider`: independent news index, enabled by `BRAVE_SEARCH_API_KEY` in the weekly premium-search slot.
- `newsapi_provider`: broader media coverage, enabled by `NEWSAPI_KEY` in the weekly premium-search slot.

Provider failures should be isolated. One failed provider or one failed company source should not fail the entire pipeline run.

## GitHub Actions

The `News Intelligence Pipeline` workflow refreshes data and commits updated JSON:

```text
data/news/latest/
docs/data/news/latest/
```

Current scheduled behavior:

- The six-hour open-source run combines balanced RSS with Spaceflight News API.
- A weekly premium-search slot queries SerpApi, Brave News, and NewsAPI when their secrets are configured.
- Runs the daily briefing at 01:15 UTC; `OPENAI_API_KEY` enables the AI summary, otherwise a rule-based summary is still published.
- Uses a single `news-data-writer` concurrency group to avoid simultaneous writes to `latest`.
- Supports manual `workflow_dispatch` inputs for `company_id`, `provider_id`, `scheduled_slot`, and `max_gdelt_queries`.
- Reads optional `SERPAPI_KEY`, `BRAVE_SEARCH_API_KEY`, and `NEWSAPI_KEY` from GitHub Secrets for the weekly search slot.

The `Build Observable Dashboard` workflow builds `observable/` into `docs/observable/` when dashboard source or latest data changes.

## Run Locally

Install:

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m ensurepip --upgrade
python -m pip install --upgrade pip setuptools wheel
python -m pip install -e ".[dev]"
```

Dry run:

```bash
python -m satellite_news
```

Current production-like RSS run:

```bash
PYTHONPATH=src python3 -m satellite_news \
  --no-dry-run \
  --provider-id rss_provider \
  --output-dir data/news/latest \
  --publish-dir docs/data/news
```

Manual partial provider run:

```bash
PYTHONPATH=src python3 -m satellite_news \
  --no-dry-run \
  --company-id spacex \
  --provider-id rss_provider \
  --scheduled-slot manual-spacex-rss \
  --output-dir data/news/latest \
  --publish-dir docs/data/news
```

Run checks:

```bash
python -m compileall -q src tests
python -m pytest
```

## Frontend

The public frontend reads:

```text
docs/data/news/latest/pipeline_result.json
docs/data/news/archive/catalog.json
docs/data/news/archive/index.json
docs/data/reports/latest/daily_report.json
```

The static frontend lives in `docs/`. The Observable Framework prototype lives in `observable/` and is built into:

```text
docs/observable/
```

The frontend does not call RSS, GDELT, LLM providers, or search APIs directly. It only reads the published JSON produced by the pipeline.

## Next Milestones

1. Tune the quality gate with reviewed false-positive and false-negative samples.
2. Add first-party company newsroom feeds and regional space-industry sources.
3. Keep GDELT paused unless used in low-frequency manual or partial slots.
4. Add topic clustering so repeated coverage becomes one event with multiple sources.
5. Measure source coverage and missing-company rates in the diagnostics panel.
