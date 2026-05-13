"""
Central configuration loader.

This module provides the AppConfig class which discovers, loads, and merges
application configuration from YAML files and environment variable overrides,
and instantiates the appropriate configuration source backend.
"""

import os
from pathlib import Path
from typing import Any, Dict, Optional

import yaml

from ..interfaces.configuration_source import ConfigurationSource
from .sources import DynamoDBConfigSource, LocalFileConfigSource, S3ConfigSource


class AppConfig:
    """Central application configuration."""

    def __init__(self, config_path: Optional[str] = None):
        """Initialize application configuration from the given or auto-discovered config path."""
        self.config_path = config_path or self._find_config()
        self.config = self._load_config()

    def _find_config(self) -> str:
        """Find config file in standard locations."""
        search_paths = [
            "src/config/app_config.yaml",
            "config/app_config.yaml",
            "/etc/contract-governor/config.yaml",
        ]

        return next(
            (path for path in search_paths if Path(path).exists()),
            "src/config/app_config.yaml",
        )

    def _load_config(self) -> Dict[str, Any]:
        """Load configuration from YAML file."""
        config_file = Path(self.config_path)

        if not config_file.exists():
            raise FileNotFoundError(f"Config file not found: {self.config_path}")

        with open(config_file, "r") as f:
            config = yaml.safe_load(f)

        # Override with environment variables
        config = self._apply_env_overrides(config)

        return config

    def _apply_env_overrides(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """Apply environment variable overrides."""
        # CONFIG_SOURCE_TYPE overrides config_source.type
        if os.getenv("CONFIG_SOURCE_TYPE"):
            config.setdefault("config_source", {})["type"] = os.getenv("CONFIG_SOURCE_TYPE")

        # S3_BUCKET overrides S3 bucket name
        if os.getenv("S3_BUCKET"):
            config.setdefault("config_source", {}).setdefault("s3", {})["bucket_name"] = os.getenv("S3_BUCKET")

        # AWS_PROFILE overrides AWS profile
        if os.getenv("AWS_PROFILE"):
            config.setdefault("aws", {})["profile"] = os.getenv("AWS_PROFILE")

        # AWS_REGION overrides AWS region
        if os.getenv("AWS_REGION"):
            config.setdefault("aws", {})["region"] = os.getenv("AWS_REGION")

        return config

    def get_config_source(self) -> ConfigurationSource:
        """Create configuration source based on config."""
        source_type = self.config.get("config_source", {}).get("type", "local_file")

        if source_type == "local_file":
            directory = (
                self.config.get("config_source", {}).get("local_file", {}).get("directory", "config/stipulations")
            )
            return LocalFileConfigSource(directory)

        elif source_type == "s3":
            s3_config = self.config.get("config_source", {}).get("s3", {})
            bucket = s3_config.get("bucket_name")
            prefix = s3_config.get("prefix", "stipulations/")
            region = s3_config.get("region", "us-east-1")

            if not bucket:
                raise ValueError("S3 bucket_name required when config_source.type is 's3'")

            return S3ConfigSource(bucket, prefix, region)

        elif source_type == "dynamodb":
            dynamodb_config = self.config.get("config_source", {}).get("dynamodb", {})
            table_name = dynamodb_config.get("table_name")
            region = dynamodb_config.get("region", "us-east-1")

            if not table_name:
                raise ValueError("DynamoDB table_name required when config_source.type is 'dynamodb'")

            return DynamoDBConfigSource(table_name, region)

        else:
            raise ValueError(f"Unknown config_source type: {source_type}")

    def get(self, key: str, default: Any = None) -> Any:
        """Get configuration value by dot-notation key."""
        keys = key.split(".")
        value: Any = self.config

        for k in keys:
            if not isinstance(value, dict):
                return default

            value = value.get(k)
            if value is None:
                return default
        return value
