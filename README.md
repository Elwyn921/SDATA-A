# SDATA A

SDATA A now includes a GitHub-native news intelligence pipeline. GitHub Actions can collect RSS/Atom sources on a schedule, normalize and score signals, then write the latest brief back into the repository.

## News Intelligence Pipeline

- Sources and topic taxonomy: `config/news_sources.json`
- LLM Summary & Report Agent prompt: `docs/llm-summary-report-agent-prompt.md`
- Pipeline executable: `src/news_pipeline.py`
- GitHub orchestration: `.github/workflows/news-intelligence.yml`
- Latest generated outputs: `data/news/latest/`
- Architecture notes: `docs/news-intelligence-architecture.md`

The Summary & Report Agent contract is:

- strict JSON output for any LLM enrichment step
- news event classification
- 0-100 importance scoring and priority labels
- Excel generation: `data/news/latest/news-report.xlsx`
- Markdown weekly report: `data/news/latest/weekly-report.md`
- GitHub Pages-ready content: `data/news/latest/pages/index.html`

The Fetcher & Source Agent supports these source types:

- `rss`, `atom`, `feed`: RSS/Atom XML feeds
- `official_website`, `website`: same-domain official-site link extraction with include/exclude patterns
- `gdelt`: GDELT 2.1 document API queries
- `newsapi`: NewsAPI `/v2/everything`, using `NEWSAPI_KEY` or a per-source `api_key_env`
- `serpapi`: SerpApi Google News search, using `SERPAPI_KEY` or a per-source `api_key_env`

All fetchers emit the shared `raw_article.v1` schema before dedupe, scoring, and report generation. Request timeout, retry, exponential backoff, and global rate limiting are configured in `config/news_sources.json` under `pipeline`.

Run locally with the deterministic fixture:

```bash
python3 -m pip install -r requirements-dev.txt
python3 -m pytest
python3 src/news_pipeline.py --config config/news_sources.json --fixture tests/fixtures/rss.xml --out data/news/latest --max-items 10
```

Run against live sources:

```bash
python3 src/news_pipeline.py --config config/news_sources.json --out data/news/latest --max-items 80
```
