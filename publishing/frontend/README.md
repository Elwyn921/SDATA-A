# A7 Frontend Prototype

This directory contains a static browser prototype for the four-company satellite news dashboard.

## Files

- `index.html` is the frontend entry point.
- `assets/app.js` renders cards, filters, the latest-news list, credibility tags, the timeline, and the archive placeholder.
- `assets/mock-pipeline-result.js` contains sample data shaped like `PipelineResult` with nested `NewsItem` records.
- `assets/pipeline-data.js` is the reserved adapter for future JSON output from `data/news/latest` or `data/news/archive`.

## Data Contract

The mock object follows the Python contract in `src/satellite_news/schema.py`:

- `PipelineResult.run_id`
- `PipelineResult.items[]`
- `PipelineResult.summaries[]`
- `PipelineResult.exports[]`
- `PipelineResult.fetch_statuses[]`
- `PipelineResult.warnings[]`

Each sample news record includes the `NewsItem` fields needed by the UI, including `company_id`, `company_name`, `title`, `url`, `published_at`, `tags`, `metadata`, and nested `source.rank_group`.

## Future Data Hook

When real export files exist, update `assets/pipeline-data.js` to load:

- `../../data/news/latest/pipeline_result.json`
- `../../data/news/archive/index.json`

No backend or external API is required for this prototype.
