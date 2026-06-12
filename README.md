# SDATA A

SDATA A is a GitHub-native satellite news intelligence pipeline architecture.

The first implementation target is periodic monitoring for SpaceX, Blue Origin, 垣信卫星, and 中国星网. The design is intentionally interface-first so the project can later expand to more companies from the satellite industry chain Mapping table.

## Scope

This repository currently defines architecture, configuration contracts, shared schemas, and module interfaces only.

It does not call real APIs, crawl websites, run LLM summaries, or export production reports yet.

## Project Structure

```text
config/
  companies.yaml          Company registry and aliases
  sources.yaml            Source registry and future adapter options
  source_rank.yaml        Source credibility and ordering policy
  prompt_templates.yaml   Prompt contracts for future LLM agents
data/
  news/                   Reserved output area
src/
  satellite_news/
    schema.py             Unified data structures
    pipeline.py           Empty fetch -> process -> summarize -> export flow
    fetcher/              Fetcher interface and stub
    processing/           Processing interface and stub
    llm/                  LLM summarizer interface and stub
    exporter/             Export interface and stub
    storage/              Storage interface and stub
tests/
  test_imports.py         Import/static architecture contract checks
```

## Pipeline Contract

The main flow is:

```text
fetch -> process -> summarize -> export
```

Each stage is decoupled behind a typed interface:

- `SourceFetcher`: future RSS, GDELT, official-site, or search adapters
- `NewsProcessor`: future normalization, dedupe, company matching, source ranking
- `NewsSummarizer`: future LLM summary and event extraction
- `NewsExporter`: future Markdown, JSON, Excel, HTML, or GitHub Pages outputs
- `PipelineStorage`: future local file, GitHub artifact, or object storage persistence

All modules exchange the unified dataclasses in `src/satellite_news/schema.py`.

## Local Checks

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m ensurepip --upgrade
python -m pip install --upgrade pip setuptools wheel
python -m pip install -e ".[dev]"
python -m compileall -q src tests
python -m pytest tests/test_imports.py tests/test_prompt_templates.py
```

## Reserved Integrations

- GitHub Actions scheduled execution
- GDELT document search
- LLM-based structured summaries
- Excel report export
- GitHub artifact and Pages publishing
