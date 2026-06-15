# SDATA A

SDATA A is a GitHub-native satellite news intelligence pipeline for monitoring SpaceX, Blue Origin, 垣信卫星, and 中国星网. The project has moved beyond architecture-only scaffolding and now has a first live data loop built around GDELT, JSON archive outputs, and a GitHub Pages frontend.

## Current Status

Implemented:

- Company and source registries for SpaceX, Blue Origin, 垣信卫星, and 中国星网.
- GDELT live fetch support for the four-company monitoring set.
- Unified `PipelineResult`, `NewsItem`, `RawArticle`, and fetch-status data contracts.
- JSON outputs under `data/news/latest/`.
- Long-lived archive structure under `data/news/archive/`.
- GitHub Pages frontend under `docs/`.
- Frontend data adapter that reads `docs/data/news/latest/pipeline_result.json` and falls back to mock data when real JSON is unavailable.

Not enabled yet:

- LLM summaries, event interpretation, and importance scoring.
- RSS fetchers.
- Official website crawlers.
- NewsAPI / SerpApi adapters.
- Excel or PDF report export.
- Fully automated live-fetch commit workflow.

## Important Runtime Note

The GDELT API is an external public service. Live runs can return `HTTP 429 Too Many Requests` when rate-limited. A 429 is recorded as a per-company fetch status and does not mean the whole pipeline or frontend is broken.

## Project Structure

```text
config/
  companies.yaml          Company registry, aliases, keywords, and industry-chain tags
  sources.yaml            Source registry, including active GDELT query configuration
  source_rank.yaml        Source credibility and ranking policy
  prompt_templates.yaml   Placeholder contracts for future LLM enrichment
data/
  news/latest/            Latest generated JSON outputs
  news/archive/           Historical run archive and archive index
docs/
  index.html              GitHub Pages frontend entry point
  assets/                 Frontend JavaScript, mock data, and styles
  data/news/latest/       Published JSON consumed by the frontend
src/
  satellite_news/
    schema.py             Unified data structures
    config.py             YAML config loaders
    pipeline.py           Fetch -> process -> summarize -> export orchestration
    provider/             Multi-source NewsProvider contracts and placeholder registry
    fetcher/gdelt.py      GDELT fetcher and HTTP transport
    processing/           Processing interface, currently pass-through
    llm/                  LLM summarizer interface, currently no-op
    exporter/             Export interface, currently no-op
    storage/json_file.py  JSON latest/archive storage
tests/
  test_imports.py
  test_gdelt_fetcher.py
  test_json_storage.py
  test_prompt_templates.py
```

## Data Flow

```text
companies.yaml + sources.yaml
        ->
NewsProvider / fetcher layer
        ->
RawArticle / NewsItem
        ->
PipelineResult
        ->
data/news/latest/*.json + data/news/archive/**
        ->
docs/data/news/latest/pipeline_result.json
        ->
GitHub Pages dashboard
```

## Provider Contract

`config/sources.yaml` defines provider contracts for:

- `official_site_provider`
- `gdelt_provider`
- `rss_provider`
- `serpapi_provider`
- `newsapi_provider`

Each provider has `priority`, `fallback`, and optional `company_overrides`. Provider implementations must output `RawArticle`; downstream modules consume normalized `NewsItem`. RSS and official-page providers now have per-company source configuration in `config/sources.yaml`; SerpApi and NewsAPI require their API key environment variables before they can run live.

## Run Locally

Install:

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m ensurepip --upgrade
python -m pip install --upgrade pip setuptools wheel
python -m pip install -e ".[dev]"
```

Dry run, no external API call:

```bash
python -m satellite_news
```

Live GDELT run:

```bash
python -m satellite_news --no-dry-run
```

Run checks:

```bash
python -m compileall -q src tests
python -m pytest
```

## Frontend

The GitHub Pages frontend lives in `docs/`.

It reads:

```text
docs/data/news/latest/pipeline_result.json
```

If that file is missing or cannot be loaded, the frontend uses:

```text
docs/assets/mock-pipeline-result.js
```

The page labels the data source as either `live JSON` or `mock fallback`.

## Next Milestones

1. Improve GDELT rate-limit handling and query quality.
2. Add A4 processing: URL normalization, dedupe, company-match validation, and source-rank filtering.
3. Add A6 LLM enrichment after data quality stabilizes.
4. Add scheduled live fetch and automated JSON publication through GitHub Actions.
5. Add RSS and official-source adapters after the GDELT loop is stable.
