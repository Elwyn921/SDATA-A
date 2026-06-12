"""YAML config loading for the minimal fetcher stage."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from satellite_news.schema import Company, SourceConfig, SourceType


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
        companies.append(
            Company(
                id=str(row["id"]),
                canonical_name=str(row["canonical_name"]),
                aliases=tuple(str(value) for value in row.get("aliases", ())),
                country_or_region=str(row.get("country_or_region", "")),
                sector_tags=tuple(str(value) for value in row.get("sector_tags", ())),
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
    core_fields = {"id", "type", "rank_group", "enabled", "description"}
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
                options=options,
            )
        )
    return tuple(sources)
