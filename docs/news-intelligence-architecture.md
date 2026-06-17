# GitHub-Native Satellite News Intelligence Pipeline

This document records the current SDATA A architecture. The project now has a live GDELT-based data loop, JSON persistence, and a GitHub Pages frontend. Some downstream intelligence features remain intentionally disabled until the data layer is more stable.

## Main Flow

```text
fetch -> process -> summarize -> export -> store -> publish
```

Current implementation:

- `fetch`: implemented for GDELT.
- `process`: pass-through placeholder.
- `summarize`: no-op placeholder.
- `export`: no-op placeholder.
- `store`: JSON latest/archive storage.
- `publish`: JSON copied into `docs/data/news/` for GitHub Pages.

## Configuration Contracts

- `config/companies.yaml`: company registry for SpaceX, Blue Origin, 垣信卫星, 中国星网, and future Mapping-table additions.
- `config/sources.yaml`: source registry, including active GDELT query configuration and reserved RSS / official-site / search sources.
- `config/sources.yaml.providers`: multi-source provider contracts with priority, fallback, and per-company overrides.
- `config/source_rank.yaml`: source credibility ranking and dedupe policy.
- `config/prompt_templates.yaml`: placeholder contracts for future LLM summarization. No LLM call is enabled yet.

## Code Contracts

- `src/satellite_news/schema.py`: shared dataclasses exchanged by every module.
- `src/satellite_news/config.py`: YAML config loading.
- `src/satellite_news/pipeline.py`: pipeline orchestration and CLI entry point.
- `src/satellite_news/provider/interface.py`: `NewsProvider` protocol, `ProviderResult`, fallback-ready registry, and no-op provider.
- `src/satellite_news/fetcher/gdelt.py`: GDELT request building, HTTP transport, response mapping, and fetch status recording.
- `src/satellite_news/processing/interface.py`: processing protocol and pass-through stub.
- `src/satellite_news/llm/interface.py`: summarizer protocol and no-op stub.
- `src/satellite_news/exporter/interface.py`: exporter protocol and no-op stub.
- `src/satellite_news/storage/json_file.py`: JSON latest/archive persistence and GitHub Pages data publication.

## Data Outputs

Latest run outputs:

```text
data/news/latest/pipeline_result.json
data/news/latest/items.json
data/news/latest/summaries.json
data/news/latest/fetch_statuses.json
data/news/latest/run_metadata.json
data/news/latest/manifest.json
```

Archive outputs:

```text
data/news/archive/index.json
data/news/archive/runs/YYYY/MM/DD/{run_id}/
```

Published frontend data:

```text
docs/data/news/latest/pipeline_result.json
docs/data/news/archive/index.json
```

## External Service Behavior

GDELT is a public external service. Live runs may encounter rate limits such as `HTTP 429 Too Many Requests`. The pipeline records these conditions per company in `fetch_statuses` rather than treating a single company failure as a total system failure.

## Distributed GDELT Scheduling Contract

The pipeline can be invoked as a low-frequency partial run:

```bash
python -m satellite_news \
  --company-id spacex \
  --provider-id gdelt_provider \
  --scheduled-slot slot-2026-06-17T00-spacex-gdelt \
  --max-gdelt-queries 1
```

This contract is designed to reduce GDELT 429 risk by spreading requests across scheduled slots. A partial run only updates the requested company/provider pair. Other companies must be preserved by the future A5 stale/latest merge layer.

Every fetch status from a partial run includes:

- `partial_run: true`
- `scheduled_slot`
- `scheduled_company_id`
- `scheduled_provider_id`
- `max_gdelt_queries`
- `merge_policy: A5_stale_latest_merge`

## Reserved Extensions

- RSS fetcher adapter.
- Official website fetcher adapter.
- SerpApi and NewsAPI provider adapters.
- LLM summary and event extraction adapter.
- Excel, Markdown, and PDF report exporters.
- Scheduled live fetch and automated commit/publish workflow.
