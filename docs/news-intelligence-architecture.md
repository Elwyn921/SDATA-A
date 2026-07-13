# GitHub-Native Satellite News Intelligence Pipeline

This document records the current SDATA A architecture. The project is now a live RSS-first news intelligence pipeline with JSON persistence, GitHub Actions refresh, GitHub Pages publishing, and an Observable dashboard prototype. GDELT remains implemented but is not the current production source because of repeated external 429 rate limits.

## Main Flow

```text
fetch -> process -> summarize -> export -> store -> publish -> visualize
```

Current implementation:

- `fetch`: production RSS provider; official-page and GDELT paths exist; API-key search providers are reserved.
- `process`: shared normalization contract with room for dedupe and relevance scoring.
- `summarize`: the in-pipeline summarizer remains a no-op.
- `report`: an experimental out-of-band daily-report generator exists but is not scheduled in production.
- `export`: no-op for now; report exports are reserved.
- `store`: JSON latest/archive storage with partial-run merge behavior.
- `publish`: JSON copied into `docs/data/news/` for GitHub Pages.
- `visualize`: static `docs/` frontend and Observable dashboard prototype.

## Monitoring Scope

The company registry has expanded from 4 companies to 13 companies.

| Category | Companies |
| --- | --- |
| Foreign major companies | SpaceX, Blue Origin |
| Satellite internet services | 垣信卫星, 中国星网 |
| Satellite platform and spacecraft manufacturing | 银河航天, 蓝箭鸿擎 / 鸿擎科技, 微纳星空 |
| Launch vehicles and launch services | 蓝箭航天 / LandSpace, 中科宇航 / CAS Space, 天兵科技 / Space Pioneer, 星际荣耀 / i-Space, 星河动力 / Galactic Energy, 宇石空间 |

## Configuration Contracts

- `config/companies.yaml`: company registry, aliases, keywords, and category metadata.
- `config/sources.yaml`: provider registry, RSS feeds, official-page entries, and provider priority/fallback contracts.
- `config/source_rank.yaml`: source credibility ranking and dedupe policy.
- `config/prompt_templates.yaml`: prompt contracts for the experimental A6 daily report.

## Code Contracts

- `src/satellite_news/schema.py`: shared dataclasses exchanged by modules.
- `src/satellite_news/config.py`: YAML config loading.
- `src/satellite_news/pipeline.py`: pipeline orchestration and CLI entry point.
- `src/satellite_news/provider/interface.py`: `NewsProvider` protocol, `ProviderResult`, registry behavior, and fallback-ready contract.
- `src/satellite_news/provider/`: concrete provider adapters for RSS, official pages, GDELT, and API-key search providers.
- `src/satellite_news/fetcher/gdelt.py`: GDELT request building, HTTP transport, response mapping, and fetch status recording.
- `src/satellite_news/processing/interface.py`: processing protocol.
- `src/satellite_news/llm/interface.py`: summarizer protocol and no-op implementation.
- `src/satellite_news/reporting/daily_report.py`: experimental daily-report generation and archive output.
- `src/satellite_news/exporter/interface.py`: exporter protocol and no-op implementation.
- `src/satellite_news/storage/json_file.py`: JSON latest/archive persistence, partial-run merge, and GitHub Pages data publication.

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

## Provider Strategy

Current production strategy:

1. RSS is the scheduled production provider.
2. Official pages are kept as structured source candidates, but complex crawling is intentionally avoided.
3. GDELT is paused from scheduled production because of frequent 429 rate limits.
4. Search APIs such as SerpApi, Serper, or NewsAPI should be added as optional fallback providers with quota control.
5. Missing API keys should produce a skipped status, not a failed system run.

Provider output must remain unified:

```text
provider result -> RawArticle -> NewsItem -> PipelineResult
```

One provider failure must not fail the entire pipeline.

## GitHub Actions Schedule

The `News Intelligence Pipeline` workflow currently runs every 6 hours:

```text
cron: "0 */6 * * *"
```

Scheduled runs use:

```text
--provider-id rss_provider
```

The workflow writes both repository data and Pages data:

```text
data/news/latest/
docs/data/news/latest/
```

Manual `workflow_dispatch` still supports partial-run inputs:

- `company_id`
- `provider_id`
- `scheduled_slot`
- `max_gdelt_queries`

This keeps the architecture ready for low-frequency provider experiments without changing the production RSS loop.

## Partial-Run Merge Contract

For partial runs, the storage layer merges the current run with the previous latest output:

- Updated companies use current-run data.
- Companies not touched by the partial run are retained from the previous latest output.
- Retained items are marked in metadata so the frontend can distinguish current results from retained results.
- Archive output still preserves the raw current run separately.

This protects the frontend from appearing empty when only one company or one provider is refreshed.

## External Service Behavior

GDELT is a public external service. `HTTP 429 Too Many Requests` means GDELT is rate-limiting the request. The pipeline records this as provider status. It is not a repository, frontend, or GitHub Actions crash by itself.

RSS source quality varies by feed. Some feeds may return old items, duplicate items, or broad topic matches. This is expected at the current stage and should be improved through source ranking, keyword tightening, and dedupe rather than by making the fetch loop brittle.

## Reserved Extensions

- Production scheduling and frontend integration for LLM daily reports.
- Event extraction and importance scoring.
- Company profile updates based on accumulated news.
- Search API fallback with quota-aware scheduling.
- Excel, Markdown, PDF, and website report exports.
- More satellite industry-chain company groups.
