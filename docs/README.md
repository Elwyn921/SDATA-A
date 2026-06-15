# SDATA A GitHub Pages Prototype

This directory is the GitHub Pages publishing root for the A7 frontend prototype.

## Entry

- `index.html` is the public dashboard page.
- `assets/mock-pipeline-result.js` contains sample `PipelineResult` data.
- `assets/pipeline-data.js` reserves the future JSON loading adapter.

## Future JSON Paths

When export jobs are available, publish generated JSON under:

- `data/news/latest/pipeline_result.json`
- `data/news/archive/index.json`

The current page intentionally loads mock data only and does not call external APIs.
