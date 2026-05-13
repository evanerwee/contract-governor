"""
Utility functions for configuration management, hot-reloading, and versioning.

This module provides helper functions to set up and manage configuration
systems with hot-reloading and versioning capabilities.
"""

import json
import logging
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..core.models import StipulationConfig
from ..interfaces.configuration_source import ConfigurationSource
from .manager import ConfigurationManager, ConfigurationVersionManager
from .sources import DynamoDBConfigSource, LocalFileConfigSource, S3ConfigSource

logger = logging.getLogger(__name__)


def create_configuration_manager(
    config_sources: List[Dict[str, Any]],
    cache_ttl: int = 300,
    enable_hot_reload: bool = True,
    hot_reload_interval: int = 60,
) -> ConfigurationManager:
    """
    Create a configuration manager with multiple sources and hot-reloading.

    Args:
        config_sources: List of source configurations
        cache_ttl: Cache time-to-live in seconds
        enable_hot_reload: Whether to enable hot-reloading
        hot_reload_interval: Hot-reload check interval in seconds

    Returns:
        Configured ConfigurationManager instance

    Example::

        config_sources = [
            {"type": "local_file", "config_dir": "config/stipulations"},
            {"type": "s3", "bucket_name": "my-config-bucket", "prefix": "stipulations/"},
            {"type": "dynamodb", "table_name": "stipulations-config"}
        ]
        manager = create_configuration_manager(config_sources)
    """
    sources: list[ConfigurationSource] = []

    for source_config in config_sources:
        source_type = source_config.get("type")

        if source_type == "local_file":
            config_dir = source_config.get("config_dir", "config/stipulations")
            sources.append(LocalFileConfigSource(config_dir))

        elif source_type == "s3":
            bucket_name = source_config["bucket_name"]
            prefix = source_config.get("prefix", "stipulations/")
            region = source_config.get("region", "us-east-1")
            sources.append(S3ConfigSource(bucket_name, prefix, region))

        elif source_type == "dynamodb":
            table_name = source_config["table_name"]
            region = source_config.get("region", "us-east-1")
            sources.append(DynamoDBConfigSource(table_name, region))

        else:
            logger.warning(f"Unknown source type: {source_type}")

    if not sources:
        raise ValueError("At least one configuration source must be specified")

    manager = ConfigurationManager(sources, cache_ttl)

    # Load validation schema if available
    schema_path = Path("config/stipulations/schema.json")
    if schema_path.exists():
        try:
            with open(schema_path) as f:
                schema = json.load(f)
            manager.set_validation_schema(schema)
            logger.info("Loaded configuration validation schema")
        except Exception as e:
            logger.warning(f"Failed to load validation schema: {e}")

    # Enable hot-reloading if requested
    if enable_hot_reload:
        manager.enable_hot_reload(hot_reload_interval)

    return manager


def create_versioned_manager(base_manager: ConfigurationManager, max_versions: int = 10) -> ConfigurationVersionManager:
    """
    Create a versioned configuration manager.

    Args:
        base_manager: Base ConfigurationManager instance
        max_versions: Maximum number of versions to keep per configuration

    Returns:
        ConfigurationVersionManager instance
    """
    return ConfigurationVersionManager(base_manager, max_versions)


def setup_change_monitoring(manager: ConfigurationManager, audit_log_path: str = "logs/config_changes.log") -> None:
    """
    Set up configuration change monitoring and audit logging.

    Args:
        manager: ConfigurationManager instance
        audit_log_path: Path to audit log file
    """
    # Ensure log directory exists
    log_dir = Path(audit_log_path).parent
    log_dir.mkdir(parents=True, exist_ok=True)

    def audit_change_listener(key: str, config: Optional[StipulationConfig], action: str):
        """Log configuration changes for audit purposes."""
        timestamp = datetime.now(timezone.utc).isoformat()

        audit_entry = {
            "timestamp": timestamp,
            "stipulation_key": key,
            "action": action,
            "config_hash": None,
            "stipulation_id": None,
            "stipulation_version": None,
        }

        if config:
            import hashlib
            from dataclasses import asdict

            config_dict = asdict(config)
            config_hash = hashlib.sha256(json.dumps(config_dict, sort_keys=True).encode()).hexdigest()

            audit_entry.update(
                {
                    "config_hash": config_hash,
                    "stipulation_id": config.stipulation_id,
                    "stipulation_version": config.stipulation_version,
                }
            )

        # Write to audit log
        try:
            with open(audit_log_path, "a") as f:
                f.write(json.dumps(audit_entry) + "\n")
        except Exception as e:
            logger.error(f"Failed to write audit log: {e}")

        logger.info(f"Configuration {action}: {key}")

    manager.add_change_listener(audit_change_listener)
    logger.info(f"Configuration change monitoring enabled, audit log: {audit_log_path}")


def backup_configurations(manager: ConfigurationManager, backup_dir: str = "backups/configurations") -> str:
    """
    Create a backup of all current configurations.

    Args:
        manager: ConfigurationManager instance
        backup_dir: Directory to store backups

    Returns:
        Path to the created backup file
    """
    backup_path = Path(backup_dir)
    backup_path.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    backup_file = backup_path / f"stipulations_backup_{timestamp}.json"

    try:
        # Load all configurations
        all_configs = manager.load_all_stipulations(use_cache=False)

        # Convert to serializable format
        backup_data: dict[str, Any] = {
            "backup_timestamp": datetime.now(timezone.utc).isoformat(),
            "total_configurations": len(all_configs),
            "configurations": {},
        }

        for key, config in all_configs.items():
            from dataclasses import asdict

            backup_data["configurations"][key] = asdict(config)

        # Write backup file
        with open(backup_file, "w") as f:
            json.dump(backup_data, f, indent=2, sort_keys=True)

        logger.info(f"Created configuration backup: {backup_file}")
        return str(backup_file)

    except Exception as e:
        logger.error(f"Failed to create configuration backup: {e}")
        raise


def restore_configurations(
    manager: ConfigurationManager, backup_file: str, target_source: int = 0, dry_run: bool = False
) -> Dict[str, bool]:
    """
    Restore configurations from a backup file.

    Args:
        manager: ConfigurationManager instance
        backup_file: Path to backup file
        target_source: Index of target source for restoration
        dry_run: If True, only validate without actually restoring

    Returns:
        Dictionary mapping configuration keys to restoration success status
    """
    results: dict[str, bool] = {}

    try:
        with open(backup_file) as f:
            backup_data = json.load(f)

        configurations = backup_data.get("configurations", {})
        logger.info(f"Restoring {len(configurations)} configurations from {backup_file}")

        for key, config_dict in configurations.items():
            try:
                # Parse category and version from key
                category, api_major = key.split(":", 1)

                # Create StipulationConfig object
                config = StipulationConfig(**config_dict)

                if dry_run:
                    # Just validate the configuration
                    validation_result = manager._validate_config(config)
                    results[key] = validation_result.is_valid
                    if not validation_result.is_valid:
                        logger.warning(f"Invalid configuration {key}: {validation_result.errors}")
                else:
                    # Actually restore the configuration
                    success = manager.save_stipulation(category, api_major, config, target_source)
                    results[key] = success

                    if success:
                        logger.info(f"Restored configuration: {key}")
                    else:
                        logger.error(f"Failed to restore configuration: {key}")

            except Exception as e:
                logger.error(f"Failed to restore configuration {key}: {e}")
                results[key] = False

        if dry_run:
            logger.info("Dry run completed - no configurations were actually restored")
        else:
            successful = sum(1 for success in results.values() if success)
            logger.info(f"Restoration completed: {successful}/{len(results)} configurations restored")

        return results

    except Exception as e:
        logger.error(f"Failed to restore configurations from {backup_file}: {e}")
        raise


def validate_configuration_integrity(manager: ConfigurationManager) -> Dict[str, Any]:
    """
    Validate the integrity of all configurations across sources.

    Args:
        manager: ConfigurationManager instance

    Returns:
        Dictionary with validation results and statistics
    """
    results: dict[str, Any] = {
        "total_configurations": 0,
        "valid_configurations": 0,
        "invalid_configurations": 0,
        "source_availability": [],
        "validation_errors": [],
        "warnings": [],
    }

    # Check source availability
    for i, source in enumerate(manager.sources):
        source_info = {"index": i, "type": source.__class__.__name__, "available": source.is_available()}

        try:
            source_info.update(source.get_source_info())
        except Exception as e:
            source_info["error"] = str(e)

        results["source_availability"].append(source_info)

    # Validate all configurations
    try:
        all_configs = manager.load_all_stipulations(use_cache=False)
        results["total_configurations"] = len(all_configs)

        for key, config in all_configs.items():
            validation_result = manager._validate_config(config)

            if validation_result.is_valid:
                results["valid_configurations"] += 1
            else:
                results["invalid_configurations"] += 1
                results["validation_errors"].append({"key": key, "errors": validation_result.errors})

            if validation_result.warnings:
                results["warnings"].extend([{"key": key, "warning": warning} for warning in validation_result.warnings])

    except Exception as e:
        results["validation_errors"].append({"key": "global", "errors": [f"Failed to load configurations: {e}"]})

    return results


def export_configurations_to_format(
    manager: ConfigurationManager, output_dir: str, format_type: str = "yaml"
) -> List[str]:
    """
    Export all configurations to files in a specific format.

    Args:
        manager: ConfigurationManager instance
        output_dir: Directory to write exported files
        format_type: Export format ("yaml" or "json")

    Returns:
        List of created file paths
    """
    if format_type not in ["yaml", "json"]:
        raise ValueError("format_type must be 'yaml' or 'json'")

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    created_files = []

    try:
        all_configs = manager.load_all_stipulations(use_cache=False)

        for key, config in all_configs.items():
            category, api_major = key.split(":", 1)
            filename = f"{category}_{api_major}.{format_type}"
            file_path = output_path / filename

            from dataclasses import asdict

            config_dict = asdict(config)

            if format_type == "yaml":
                import yaml

                with open(file_path, "w") as f:
                    yaml.dump(config_dict, f, default_flow_style=False, sort_keys=True)
            else:  # json
                with open(file_path, "w") as f:
                    json.dump(config_dict, f, indent=2, sort_keys=True)

            created_files.append(str(file_path))
            logger.info(f"Exported configuration {key} to {file_path}")

        logger.info(f"Exported {len(created_files)} configurations to {output_dir}")
        return created_files

    except Exception as e:
        logger.error(f"Failed to export configurations: {e}")
        raise


class ConfigurationWatcher:
    """
    File system watcher for configuration changes with immediate reload.
    """

    def __init__(self, manager: ConfigurationManager, watch_dirs: List[str]):
        """
        Initialize configuration watcher.

        Args:
            manager: ConfigurationManager instance
            watch_dirs: List of directories to watch for changes
        """
        self.manager = manager
        self.watch_dirs = [Path(d) for d in watch_dirs]
        self._watching = False
        self._watch_thread: threading.Thread | None = None
        self._stop_event = threading.Event()

    def start_watching(self) -> None:
        """Start watching for configuration file changes."""
        if self._watching:
            return

        self._watching = True
        self._stop_event.clear()

        def watch_worker():
            """Poll watched directories for configuration file changes and trigger reloads."""
            file_mtimes = {}

            while not self._stop_event.wait(1):  # Check every second
                try:
                    for watch_dir in self.watch_dirs:
                        if not watch_dir.exists():
                            continue

                        for file_path in watch_dir.glob("*.yaml"):
                            self._check_file_change(file_path, file_mtimes)

                        for file_path in watch_dir.glob("*.json"):
                            self._check_file_change(file_path, file_mtimes)

                except Exception as e:
                    logger.error(f"Error in configuration watcher: {e}")

        self._watch_thread = threading.Thread(target=watch_worker, daemon=True)
        self._watch_thread.start()

        logger.info(f"Started watching configuration directories: {self.watch_dirs}")

    def stop_watching(self) -> None:
        """Stop watching for configuration file changes."""
        if not self._watching:
            return

        self._watching = False
        self._stop_event.set()

        if self._watch_thread:
            self._watch_thread.join(timeout=5)

        logger.info("Stopped watching configuration directories")

    def _check_file_change(self, file_path: Path, file_mtimes: Dict[str, float]) -> None:
        """Check if a file has changed and reload if necessary."""
        try:
            current_mtime = file_path.stat().st_mtime

            if str(file_path) in file_mtimes:
                if file_mtimes[str(file_path)] != current_mtime:
                    # File changed, reload configuration
                    logger.info(f"Configuration file changed: {file_path}")
                    self.manager.clear_cache()

                    # Trigger reload of specific configuration
                    try:
                        category, api_major = self._parse_filename(file_path.stem)
                        config = self.manager.load_stipulation(category, api_major, use_cache=False)
                        if config:
                            logger.info(f"Reloaded configuration: {category}:{api_major}")
                    except Exception as e:
                        logger.error(f"Failed to reload configuration from {file_path}: {e}")

            file_mtimes[str(file_path)] = current_mtime

        except Exception as e:
            logger.error(f"Error checking file {file_path}: {e}")

    def _parse_filename(self, filename: str) -> tuple[str, str]:
        """Parse category and API major version from filename."""
        parts = filename.split("_")
        if len(parts) < 2:
            raise ValueError(f"Invalid filename format: {filename}")

        api_major = parts[-1]
        category = "_".join(parts[:-1])

        return category, api_major
