"""Storage interfaces and JSON file persistence."""

from satellite_news.storage.interface import NullStorage, PipelineStorage
from satellite_news.storage.json_file import JsonFileStorage

__all__ = ["JsonFileStorage", "NullStorage", "PipelineStorage"]
