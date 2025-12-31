"""
UN Documents ETL Package

This package provides loaders to extract data from parsed JSON files
and load them into the PostgreSQL database.
"""

from etl.base import BaseLoader
from etl.load_resolutions import ResolutionLoader

__all__ = ['BaseLoader', 'ResolutionLoader']
