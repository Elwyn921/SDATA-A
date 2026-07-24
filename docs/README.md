# Commercial Space Intelligence GitHub Pages Frontend

This directory is the GitHub Pages publishing root for the SDATA A satellite news dashboard.

The frontend is now connected to live pipeline JSON produced by the RSS data loop. It does not call news providers directly; it only reads JSON files published by the pipeline.

## Entry Points

- `index.html` is the main static dashboard page.
- `assets/app.js` renders the dashboard UI.
- `assets/pipeline-data.js` validates the latest run manifest, loads current data first,
  and defers the large archive catalog and event timeline.
- `assets/mock-pipeline-result.js` is only loaded when mock mode is explicitly requested.
- `demo/index.html` keeps the original demo URL and redirects to the new visual
  exploration frontend in `demo-next/`.
- The retired frontend is preserved outside the Pages root at
  `frontend-disabled/legacy-main/`.
- `observable/` contains the built Observable dashboard output.

## Live Data Paths

The frontend reads:

```text
docs/data/news/latest/pipeline_result.json
docs/data/news/latest/manifest.json
docs/data/news/archive/index.json
docs/data/news/archive/catalog.json
docs/data/news/latest/event_timeline.json
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

## Data Source Behavior

The page checks the small latest-run manifest without using a stale browser copy. The
run id is then attached to JSON requests so a new GitHub publication is picked up
immediately while unchanged files remain cacheable. The latest news and headline
indices render first; archive and event data load after first paint or on demand.

GDELT is not called by the frontend. GDELT 429 rate limits are external service behavior and should be shown, if needed, as provider health information rather than a frontend failure.
