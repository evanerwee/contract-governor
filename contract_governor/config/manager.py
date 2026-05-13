"""
Central configuration manager that orchestrates multiple configuration sources.

This module implements configuration precedence, caching, validation, and hot-reloading
capabilities for the stipulations system.
"""

import hashlib
import json
import logging
import threading
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Optional

from ..core.models import StipulationConfig
from ..interfaces.configuration_source import ConfigurationSource

logger = logging.getLogger(__name__)


class ConfigurationManager:
    """
    Central manager for stipulation configurations with multiple backend support.

    Implements configuration precedence (local > S3 > DynamoDB), caching,
    validation, and hot-reloading capabilities.
    """

    def __init__(self, sources: List[ConfigurationSource], cache_ttl: int = 300):
        """
        Initialize configuration manager with multiple sources.

        Args:
            sources: List of configuration sources in precedence order (highest first)
            cache_ttl: Cache time-to-live in seconds
        """
        self.sources = sources
        self.cache_ttl = cache_ttl
        self._cache: dict[str, StipulationConfig] = {}
        self._cache_timestamps: dict[str, datetime] = {}
        self._source_hashes: dict[str, str] = {}
        self._lock = threading.RLock()
        self._change_listeners: list[Callable[[str, Optional[StipulationConfig], str], None]] = []
        self._validation_schema: dict[str, Any] | None = None
        self._hot_reload_enabled = False
        self._reload_thread: threading.Thread | None = None
        self._stop_reload = threading.Event()

    def load_stipulation(
        self, category: str, api_major_version: str, use_cache: bool = True
    ) -> Optional[StipulationConfig]:
        """
        Load a stipulation configuration with precedence and caching.

        Args:
            category: API category
            api_major_version: API major version
            use_cache: Whether to use cached values

        Returns:
            StipulationConfig if found, None otherwise
        """
        key = f"{category}:{api_major_version}"

        # Check cache first if enabled
        if use_cache and self._is_cache_valid(key):
            return self._cache.get(key)

        # Load from sources in precedence order
        config = None
        source_used = None

        for source in self.sources:
            if not source.is_available():
                logger.warning(f"Configuration source {source.__class__.__name__} is not available")
                continue

            try:
                config = source.load_stipulation(category, api_major_version)
                if config:
                    source_used = source
                    break
            except Exception as e:
                logger.error(f"Failed to load from {source.__class__.__name__}: {e}")
                continue

        # Validate configuration if found
        if config:
            validation_result = self._validate_config(config)
            if not validation_result.is_valid:
                logger.error(f"Invalid configuration for {key}: {validation_result.errors}")
                return None

            # Cache the result
            with self._lock:
                self._cache[key] = config
                self._cache_timestamps[key] = datetime.now(timezone.utc)

            logger.info(f"Loaded stipulation {key} from {source_used.__class__.__name__}")

        return config

    def load_all_stipulations(self, use_cache: bool = True) -> Dict[str, StipulationConfig]:
        """
        Load all stipulation configurations from all sources with precedence.

        Args:
            use_cache: Whether to use cached values

        Returns:
            Dictionary mapping stipulation keys to configurations
        """
        all_configs = {}

        # Load from all sources in reverse precedence order (lowest first)
        for source in reversed(self.sources):
            if not source.is_available():
                continue

            try:
                source_configs = source.load_stipulations()
                for key, config in source_configs.items():
                    validation_result = self._validate_config(config)
                    if validation_result.is_valid:
                        all_configs[key] = config
                    else:
                        logger.error(
                            f"Invalid configuration {key} from {source.__class__.__name__}: {validation_result.errors}"
                        )

                logger.info(f"Loaded {len(source_configs)} stipulations from {source.__class__.__name__}")

            except Exception as e:
                logger.error(f"Failed to load all stipulations from {source.__class__.__name__}: {e}")

        # Update cache
        if use_cache:
            with self._lock:
                self._cache.update(all_configs)
                now = datetime.now(timezone.utc)
                for key in all_configs:
                    self._cache_timestamps[key] = now

        return all_configs

    def save_stipulation(
        self, category: str, api_major_version: str, config: StipulationConfig, target_source: int = 0
    ) -> bool:
        """
        Save a stipulation configuration to a specific source.

        Args:
            category: API category
            api_major_version: API major version
            config: StipulationConfig to save
            target_source: Index of target source (0 = highest precedence)

        Returns:
            True if saved successfully, False otherwise
        """
        if target_source >= len(self.sources):
            logger.error(f"Invalid target source index: {target_source}")
            return False

        # Validate configuration before saving
        validation_result = self._validate_config(config)
        if not validation_result.is_valid:
            logger.error(f"Cannot save invalid configuration: {validation_result.errors}")
            return False

        source = self.sources[target_source]
        if not source.is_available():
            logger.error(f"Target source {source.__class__.__name__} is not available")
            return False

        try:
            source.save_stipulation(category, api_major_version, config)

            # Update cache
            key = f"{category}:{api_major_version}"
            with self._lock:
                self._cache[key] = config
                self._cache_timestamps[key] = datetime.now(timezone.utc)

            # Notify change listeners
            self._notify_change_listeners(key, config, "updated")

            logger.info(f"Saved stipulation {key} to {source.__class__.__name__}")
            return True

        except Exception as e:
            logger.error(f"Failed to save stipulation to {source.__class__.__name__}: {e}")
            return False

    def delete_stipulation(self, category: str, api_major_version: str, target_source: int = 0) -> bool:
        """
        Delete a stipulation configuration from a specific source.

        Args:
            category: API category
            api_major_version: API major version
            target_source: Index of target source (0 = highest precedence)

        Returns:
            True if deleted successfully, False otherwise
        """
        if target_source >= len(self.sources):
            logger.error(f"Invalid target source index: {target_source}")
            return False

        source = self.sources[target_source]
        if not source.is_available():
            logger.error(f"Target source {source.__class__.__name__} is not available")
            return False

        try:
            success = source.delete_stipulation(category, api_major_version)

            if success:
                # Remove from cache
                key = f"{category}:{api_major_version}"
                with self._lock:
                    self._cache.pop(key, None)
                    self._cache_timestamps.pop(key, None)

                # Notify change listeners
                self._notify_change_listeners(key, None, "deleted")

                logger.info(f"Deleted stipulation {key} from {source.__class__.__name__}")

            return success

        except Exception as e:
            logger.error(f"Failed to delete stipulation from {source.__class__.__name__}: {e}")
            return False

    def list_categories(self) -> List[str]:
        """List all available API categories from all sources."""
        categories = set()

        for source in self.sources:
            if source.is_available():
                try:
                    source_categories = source.list_categories()
                    categories.update(source_categories)
                except Exception as e:
                    logger.error(f"Failed to list categories from {source.__class__.__name__}: {e}")

        return sorted(list(categories))

    def list_versions(self, category: str) -> List[str]:
        """List all available API major versions for a category from all sources."""
        versions = set()

        for source in self.sources:
            if source.is_available():
                try:
                    source_versions = source.list_versions(category)
                    versions.update(source_versions)
                except Exception as e:
                    logger.error(f"Failed to list versions from {source.__class__.__name__}: {e}")

        return sorted(list(versions))

    def get_source_info(self) -> List[Dict[str, Any]]:
        """Get information about all configuration sources."""
        info = []

        for i, source in enumerate(self.sources):
            try:
                source_info = source.get_source_info()
                source_info["precedence"] = i
                info.append(source_info)
            except Exception as e:
                info.append({"type": source.__class__.__name__, "precedence": i, "available": False, "error": str(e)})

        return info

    def clear_cache(self) -> None:
        """Clear the configuration cache."""
        with self._lock:
            self._cache.clear()
            self._cache_timestamps.clear()

        logger.info("Configuration cache cleared")

    def refresh_cache(self) -> None:
        """Refresh the configuration cache by reloading all stipulations."""
        self.clear_cache()
        self.load_all_stipulations(use_cache=True)
        logger.info("Configuration cache refreshed")

    def add_change_listener(self, listener: Callable[[str, Optional[StipulationConfig], str], None]) -> None:
        """
        Add a listener for configuration changes.

        Args:
            listener: Function called with (key, config, action) when changes occur
        """
        self._change_listeners.append(listener)

    def remove_change_listener(self, listener: Callable) -> None:
        """Remove a configuration change listener."""
        if listener in self._change_listeners:
            self._change_listeners.remove(listener)

    def enable_hot_reload(self, check_interval: int = 60) -> None:
        """
        Enable hot-reloading of configurations.

        Args:
            check_interval: Interval in seconds between checks
        """
        if self._hot_reload_enabled:
            return

        self._hot_reload_enabled = True
        self._stop_reload.clear()

        def reload_worker():
            """Periodically check for configuration changes and reload as needed."""
            while not self._stop_reload.wait(check_interval):
                try:
                    self._check_for_changes()
                except Exception as e:
                    logger.error(f"Error during hot-reload check: {e}")

        self._reload_thread = threading.Thread(target=reload_worker, daemon=True)
        self._reload_thread.start()

        logger.info(f"Hot-reload enabled with {check_interval}s interval")

    def disable_hot_reload(self) -> None:
        """Disable hot-reloading of configurations."""
        if not self._hot_reload_enabled:
            return

        self._hot_reload_enabled = False
        self._stop_reload.set()

        if self._reload_thread:
            self._reload_thread.join(timeout=5)

        logger.info("Hot-reload disabled")

    def set_validation_schema(self, schema: Dict[str, Any]) -> None:
        """
        Set JSON schema for configuration validation.

        Args:
            schema: JSON schema dictionary
        """
        self._validation_schema = schema
        logger.info("Configuration validation schema updated")

    def get_cache_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        with self._lock:
            now = datetime.now(timezone.utc)
            expired_count = sum(
                1 for ts in self._cache_timestamps.values() if now - ts > timedelta(seconds=self.cache_ttl)
            )

            return {
                "total_entries": len(self._cache),
                "expired_entries": expired_count,
                "cache_ttl": self.cache_ttl,
                "hit_ratio": getattr(self, "_cache_hits", 0) / max(getattr(self, "_cache_requests", 1), 1),
            }

    def _is_cache_valid(self, key: str) -> bool:
        """Check if cached entry is still valid."""
        if key not in self._cache or key not in self._cache_timestamps:
            return False

        age = datetime.now(timezone.utc) - self._cache_timestamps[key]
        is_valid: bool = age.total_seconds() < self.cache_ttl
        return is_valid

    def _validate_config(self, config: StipulationConfig) -> "ValidationResult":
        """Validate a stipulation configuration."""
        errors: list[str] = []
        warnings: list[str] = []

        # Basic validation
        if not config.stipulation_id:
            errors.append("stipulation_id is required")

        if not config.stipulation_version:
            errors.append("stipulation_version is required")

        if config.exposure_policy not in ["tenant-scoped", "global-control-plane", "private"]:
            errors.append(f"Invalid exposure_policy: {config.exposure_policy}")

        if not config.proxy_prefix_format:
            errors.append("proxy_prefix_format is required")

        if (
            config.requires_scope_parameter
            and config.proxy_prefix_format
            and "{tenant_id}" not in config.proxy_prefix_format
            and "{scope_id}" not in config.proxy_prefix_format
        ):
            errors.append("requires_scope_parameter is True but proxy_prefix_format lacks scope parameter")

        # JSON Schema validation if available
        if self._validation_schema:
            try:
                import jsonschema

                config_dict = asdict(config)
                jsonschema.validate(config_dict, self._validation_schema)
            except ImportError:
                warnings.append("jsonschema not available for advanced validation")
            except Exception as e:
                errors.append(f"Schema validation failed: {e}")

        return ValidationResult(is_valid=len(errors) == 0, errors=errors, warnings=warnings)

    def _notify_change_listeners(self, key: str, config: Optional[StipulationConfig], action: str) -> None:
        """Notify all change listeners of a configuration change."""
        for listener in self._change_listeners:
            try:
                listener(key, config, action)
            except Exception as e:
                logger.error(f"Error in change listener: {e}")

    def _check_for_changes(self) -> None:
        """Check for configuration changes and reload if necessary."""
        changed_keys = set()

        for source in self.sources:
            if not source.is_available():
                continue

            try:
                # Get current source hash
                source_info = source.get_source_info()
                current_hash = self._compute_source_hash(source_info)
                source_key = source.__class__.__name__

                if source_key in self._source_hashes:
                    if self._source_hashes[source_key] != current_hash:
                        # Source changed, reload configurations
                        logger.info(f"Detected changes in {source_key}, reloading...")
                        source_configs = source.load_stipulations()

                        for key, config in source_configs.items():
                            if self._should_reload_config(key, config):
                                changed_keys.add(key)
                                with self._lock:
                                    self._cache[key] = config
                                    self._cache_timestamps[key] = datetime.now(timezone.utc)

                                self._notify_change_listeners(key, config, "reloaded")

                self._source_hashes[source_key] = current_hash

            except Exception as e:
                logger.error(f"Error checking changes in {source.__class__.__name__}: {e}")

        if changed_keys:
            logger.info(f"Hot-reloaded {len(changed_keys)} configurations")

    def _compute_source_hash(self, source_info: Dict[str, Any]) -> str:
        """Compute hash of source information for change detection."""
        # Remove timestamp fields that change frequently
        filtered_info = {k: v for k, v in source_info.items() if k not in ["last_checked", "timestamp"]}

        info_str = json.dumps(filtered_info, sort_keys=True)
        return hashlib.sha256(info_str.encode()).hexdigest()

    def _should_reload_config(self, key: str, new_config: StipulationConfig) -> bool:
        """Check if a configuration should be reloaded."""
        if key not in self._cache:
            return True

        current_config = self._cache[key]

        # Compare configuration hashes
        current_hash = hashlib.sha256(json.dumps(asdict(current_config), sort_keys=True).encode()).hexdigest()
        new_hash = hashlib.sha256(json.dumps(asdict(new_config), sort_keys=True).encode()).hexdigest()

        return current_hash != new_hash


class ValidationResult:
    """Result of configuration validation."""

    def __init__(self, is_valid: bool, errors: List[str], warnings: List[str] | None = None):
        """Initialize validation result with validity flag, errors, and optional warnings."""
        self.is_valid = is_valid
        self.errors = errors
        self.warnings = warnings or []


class ConfigurationVersionManager:
    """
    Manages configuration versioning and rollback capabilities.
    """

    def __init__(self, manager: ConfigurationManager, max_versions: int = 10):
        """
        Initialize version manager.

        Args:
            manager: ConfigurationManager instance
            max_versions: Maximum number of versions to keep per configuration
        """
        self.manager = manager
        self.max_versions = max_versions
        self._versions: dict[str, list[tuple[datetime, StipulationConfig, str]]] = {}
        self._lock = threading.RLock()

    def save_version(
        self, category: str, api_major_version: str, config: StipulationConfig, version_id: str | None = None
    ) -> str:
        """
        Save a versioned configuration.

        Args:
            category: API category
            api_major_version: API major version
            config: StipulationConfig to save
            version_id: Optional version identifier

        Returns:
            Version identifier
        """
        key = f"{category}:{api_major_version}"

        if version_id is None:
            version_id = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

        with self._lock:
            if key not in self._versions:
                self._versions[key] = []

            # Add new version
            self._versions[key].append((datetime.now(timezone.utc), config, version_id))

            # Trim old versions
            if len(self._versions[key]) > self.max_versions:
                self._versions[key] = self._versions[key][-self.max_versions :]

        # Save to primary source
        success = self.manager.save_stipulation(category, api_major_version, config)

        if success:
            logger.info(f"Saved version {version_id} for {key}")

        return version_id

    def list_versions(self, category: str, api_major_version: str) -> List[Dict[str, Any]]:
        """List all versions for a configuration."""
        key = f"{category}:{api_major_version}"

        with self._lock:
            versions = self._versions.get(key, [])
            return [
                {
                    "version_id": version_id,
                    "timestamp": timestamp.isoformat(),
                    "config_hash": hashlib.sha256(json.dumps(asdict(config), sort_keys=True).encode()).hexdigest()[:8],
                }
                for timestamp, config, version_id in versions
            ]

    def rollback_to_version(self, category: str, api_major_version: str, version_id: str) -> bool:
        """
        Rollback to a specific version.

        Args:
            category: API category
            api_major_version: API major version
            version_id: Version to rollback to

        Returns:
            True if rollback successful, False otherwise
        """
        key = f"{category}:{api_major_version}"

        with self._lock:
            versions = self._versions.get(key, [])

            for timestamp, config, vid in versions:
                if vid == version_id:
                    # Save as new current version
                    success = self.manager.save_stipulation(category, api_major_version, config)

                    if success:
                        logger.info(f"Rolled back {key} to version {version_id}")

                    return success

        logger.error(f"Version {version_id} not found for {key}")
        return False
