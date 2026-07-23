"""YAML config loading for the minimal fetcher stage."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from satellite_news.schema import (
    Company,
    CompanyProviderConfig,
    FallbackMode,
    NewsProviderConfig,
    ProviderFallbackPolicy,
    SourceConfig,
    SourceType,
)


def load_yaml(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"Expected mapping in {path}")
    return data


def load_companies(path: Path = Path("config/companies.yaml")) -> tuple[Company, ...]:
    data = load_yaml(path)
    defaults = data.get("defaults", {})
    rows = data.get("companies", [])
    if not isinstance(rows, list):
        raise ValueError("companies.yaml must define a companies list.")

    companies: list[Company] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        keyword_rows = row.get("keywords", {})
        if not isinstance(keyword_rows, dict):
            keyword_rows = {}
        companies.append(
            Company(
                id=str(row["id"]),
                canonical_name=str(row["canonical_name"]),
                aliases=tuple(str(value) for value in row.get("aliases", ())),
                country_or_region=str(row.get("country_or_region", "")),
                sector_tags=tuple(str(value) for value in row.get("sector_tags", ())),
                primary_programs=tuple(str(value) for value in row.get("primary_programs", ())),
                keywords_include=tuple(
                    str(value)
                    for key in ("include", "zh_include")
                    for value in keyword_rows.get(key, ())
                ),
                keywords_exclude=tuple(
                    str(value) for value in keyword_rows.get("exclude_when_unqualified", ())
                ),
                enabled=bool(row.get("enabled", defaults.get("enabled", True))),
                priority=row.get("priority", defaults.get("priority", "medium")),
            )
        )
    return tuple(companies)


def load_sources(path: Path = Path("config/sources.yaml")) -> tuple[SourceConfig, ...]:
    data = load_yaml(path)
    defaults = data.get("defaults", {})
    rows = data.get("sources", [])
    if not isinstance(rows, list):
        raise ValueError("sources.yaml must define a sources list.")

    sources: list[SourceConfig] = []
    core_fields = {
        "id",
        "type",
        "rank_group",
        "enabled",
        "description",
        "provider_id",
        "provider_priority",
        "priority",
        "fallback_to",
    }
    for row in rows:
        if not isinstance(row, dict):
            continue
        options = {key: value for key, value in row.items() if key not in core_fields}
        sources.append(
            SourceConfig(
                id=str(row["id"]),
                type=SourceType(str(row["type"])),
                rank_group=str(row["rank_group"]),
                enabled=bool(row.get("enabled", defaults.get("enabled", True))),
                description=str(row.get("description", "")),
                provider_id=row.get("provider_id"),
                provider_priority=int(row.get("provider_priority", row.get("priority", 100))),
                fallback_to=tuple(str(value) for value in row.get("fallback_to", ())),
                options=options,
            )
        )
    return tuple(sources)


def load_providers(path: Path = Path("config/sources.yaml")) -> tuple[NewsProviderConfig, ...]:
    data = load_yaml(path)
    defaults = data.get("provider_defaults", {})
    rows = data.get("providers", [])
    if not isinstance(rows, list):
        raise ValueError("sources.yaml providers must be a list when provided.")

    providers: list[NewsProviderConfig] = []
    core_fields = {
        "id",
        "type",
        "rank_group",
        "enabled",
        "priority",
        "fallback",
        "description",
        "company_overrides",
    }
    for row in rows:
        if not isinstance(row, dict):
            continue
        fallback_row = row.get("fallback", {})
        if not isinstance(fallback_row, dict):
            fallback_row = {}
        company_rows = row.get("company_overrides", {})
        if not isinstance(company_rows, dict):
            company_rows = {}
        providers.append(
            NewsProviderConfig(
                id=str(row["id"]),
                type=SourceType(str(row["type"])),
                rank_group=str(row["rank_group"]),
                enabled=bool(row.get("enabled", defaults.get("enabled", True))),
                priority=int(row.get("priority", defaults.get("priority", 100))),
                fallback=ProviderFallbackPolicy(
                    mode=parse_fallback_mode(
                        fallback_row.get("mode", defaults.get("fallback_mode", "on_empty_or_error"))
                    ),
                    fallback_to=tuple(str(value) for value in fallback_row.get("to", ())),
                    max_fallback_depth=int(fallback_row.get("max_depth", 2)),
                ),
                description=str(row.get("description", "")),
                company_overrides={
                    str(company_id): parse_company_provider_config(str(company_id), override)
                    for company_id, override in company_rows.items()
                    if isinstance(override, dict)
                },
                options={key: value for key, value in row.items() if key not in core_fields},
            )
        )
    return tuple(sorted(providers, key=lambda provider: provider.priority))


def parse_company_provider_config(
    company_id: str,
    row: dict[str, Any],
) -> CompanyProviderConfig:
    return CompanyProviderConfig(
        company_id=company_id,
        enabled=bool(row.get("enabled", True)),
        priority=(
            int(row["priority"])
            if row.get("priority") is not None
            else None
        ),
        query_templates=tuple(str(value) for value in row.get("query_templates", ())),
        entrypoints=tuple(str(value) for value in row.get("entrypoints", ())),
        options={
            key: value
            for key, value in row.items()
            if key not in {"enabled", "priority", "query_templates", "entrypoints"}
        },
    )


def parse_fallback_mode(value: object) -> FallbackMode:
    mode = str(value)
    if mode not in {"disabled", "on_empty", "on_error", "on_empty_or_error"}:
        raise ValueError(f"Unsupported provider fallback mode: {mode}")
    return mode  # type: ignore[return-value]
