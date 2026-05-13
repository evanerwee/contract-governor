"""
Configuration module for stipulation definitions and configuration management.

This module implements the Single Responsibility Principle by focusing solely on:
- Stipulation configuration loading and parsing
- Configuration source abstraction
- Default stipulation definitions
- Configuration validation and schema enforcement
"""

from .defaults import DEFAULT_STIPULATIONS
from .manager import ConfigurationManager
from .sources import DynamoDBConfigSource, LocalFileConfigSource, S3ConfigSource

__all__ = [
    "ConfigurationManager",
    "LocalFileConfigSource",
    "S3ConfigSource",
    "DynamoDBConfigSource",
    "DEFAULT_STIPULATIONS",
]
