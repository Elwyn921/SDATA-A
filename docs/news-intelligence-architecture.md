# GitHub-Native Satellite News Intelligence Pipeline

This document records the architecture-only baseline. The repository is the control plane for configuration, scheduled execution, generated artifacts, and review history, but concrete business logic is delegated to later agents.

## Main Flow

```text
fetch -> process -> summarize -> export
```

The current `Pipeline` only wires stage interfaces together. All default implementations are no-op placeholders.

## Configuration Contracts

- `config/companies.yaml`: company registry for SpaceX, Blue Origin, 垣信卫星, 中国星网, and future Mapping-table additions.
- `config/sources.yaml`: source registry for official sites, RSS, GDELT, and future search APIs.
- `config/source_rank.yaml`: source credibility ranking and dedupe policy.
- `config/prompt_templates.yaml`: prompt contracts for future LLM summarization.

## Code Contracts

- `src/satellite_news/schema.py`: shared dataclasses exchanged by every module.
- `src/satellite_news/pipeline.py`: empty orchestration flow.
- `src/satellite_news/fetcher/interface.py`: fetcher protocol and no-op stub.
- `src/satellite_news/processing/interface.py`: processing protocol and pass-through stub.
- `src/satellite_news/llm/interface.py`: summarizer protocol and no-op stub.
- `src/satellite_news/exporter/interface.py`: exporter protocol and no-op stub.
- `src/satellite_news/storage/interface.py`: persistence protocol and no-op stub.

## Reserved Extensions

- GitHub Actions scheduled execution.
- GDELT fetcher adapter.
- RSS and official website fetcher adapters.
- LLM summary and event extraction adapter.
- Excel, Markdown, JSON, and GitHub Pages exporters.
