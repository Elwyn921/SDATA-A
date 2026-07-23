"""News-activity and aerospace market index generation."""

from __future__ import annotations

from typing import Any


__all__ = ["build_index_snapshot", "fetch_sina_quotes", "generate_index_snapshot"]


def __getattr__(name: str) -> Any:
    if name not in __all__:
        raise AttributeError(name)
    from satellite_news.market import index_snapshot

    return getattr(index_snapshot, name)
