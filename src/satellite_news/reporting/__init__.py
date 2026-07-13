"""Daily report generation layer for PipelineResult JSON artifacts."""

from __future__ import annotations

from typing import Any


__all__ = ["build_daily_report", "main"]


def __getattr__(name: str) -> Any:
    if name not in __all__:
        raise AttributeError(name)
    from satellite_news.reporting import daily_report

    return getattr(daily_report, name)
