# SDATA A GitHub Pages Frontend

This directory is the GitHub Pages publishing root for the SDATA A satellite news dashboard.

The frontend is now connected to live pipeline JSON produced by the RSS data loop. It does not call news providers directly; it only reads JSON files published by the pipeline.

## Entry Points

- `index.html` is the main static dashboard page.
- `assets/app.js` renders the dashboard UI.
- `assets/pipeline-data.js` loads `PipelineResult` JSON.
- `assets/mock-pipeline-result.js` remains available as a local fallback for UI development.
- `observable/` contains the built Observable dashboard output.

## Live Data Paths

The frontend reads:

```text
docs/data/news/latest/pipeline_result.json
docs/data/news/archive/index.json
```

These are published copies of root pipeline outputs:

```text
data/news/latest/pipeline_result.json
data/news/archive/index.json
```

## Current Data Scope

The current production data path is RSS-first and covers 13 companies:

- SpaceX
- Blue Origin
- 垣信卫星
- 中国星网
- 蓝箭航天 / LandSpace
- 中科宇航 / CAS Space
- 天兵科技 / Space Pioneer
- 星际荣耀 / i-Space
- 星河动力 / Galactic Energy
- 宇石空间
- 蓝箭鸿擎 / 鸿擎科技
- 银河航天 / GalaxySpace
- 微纳星空 / MinoSpace

Latest local snapshot:

- Run id: `08e76e21-26fb-4cb9-9362-f2906920b61b`
- Generated at: `2026-06-24T07:23:55.772959Z`
- Items: 591
- Provider: `rss_provider`

## Data Source Behavior

The page loads published JSON directly and shows an explicit data-unavailable state if loading fails. Mock data remains available only through the explicit `mode: "mock"` development option.

GDELT is not called by the frontend. GDELT 429 rate limits are external service behavior and should be shown, if needed, as provider health information rather than a frontend failure.
