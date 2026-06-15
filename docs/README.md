# SDATA A GitHub Pages Frontend

This directory is the GitHub Pages publishing root for the SDATA A satellite news dashboard.

## Entry

- `index.html` is the public dashboard page.
- `assets/app.js` renders company cards, filters, latest news, timeline entries, and archive placeholders.
- `assets/pipeline-data.js` loads real `PipelineResult` JSON first and falls back to mock data.
- `assets/mock-pipeline-result.js` contains sample data for fallback and UI development.

## Real JSON Paths

The frontend reads:

- `data/news/latest/pipeline_result.json`
- `data/news/archive/index.json`

These files are published copies of pipeline outputs generated under the repository root:

- `data/news/latest/pipeline_result.json`
- `data/news/archive/index.json`

## Data Source Behavior

The page attempts to load live JSON first. If it cannot load real JSON, it displays mock data and labels the source as `mock fallback`.

The frontend does not call GDELT, LLM providers, or any external API directly.
