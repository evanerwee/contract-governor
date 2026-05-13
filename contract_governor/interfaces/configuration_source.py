"""
Abstract interface for configuration source implementations.

This interface implements the Dependency Inversion Principle by allowing
the configuration system to work with multiple backends (files, S3, DynamoDB, etc.)
without depending on specific storage implementations.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from ..core.models import StipulationConfig


class ConfigurationSource(ABC):
    """
    Abstract interface for loading stipulation configurations from various sources.

    This interface allows the system to support multiple configuration backends
    (local files, S3, DynamoDB, etc.) through a common abstraction.
    """

    @abstractmethod
    def load_stipulations(self) -> Dict[str, StipulationConfig]:
        """
        Load all stipulation configurations from the source.

        Returns:
            Dictionary mapping stipulation keys to StipulationConfig objects
            Key format: "{category}:{api_major_version}"
        """
        pass

    @abstractmethod
    def load_stipulation(self, category: str, api_major_version: str) -> Optional[StipulationConfig]:
        """
        Load a specific stipulation configuration.

        Args:
            category: API category (e.g., "evidence-query")
            api_major_version: API major version (e.g., "v1")

        Returns:
            StipulationConfig if found, None otherwise
        """
        pass

    @abstractmethod
    def save_stipulation(self, category: str, api_major_version: str, config: StipulationConfig) -> None:
        """
        Save a stipulation configuration to the source.

        Args:
            category: API category
            api_major_version: API major version
            config: StipulationConfig to save
        """
        pass

    @abstractmethod
    def delete_stipulation(self, category: str, api_major_version: str) -> bool:
        """
        Delete a stipulation configuration from the source.

        Args:
            category: API category
            api_major_version: API major version

        Returns:
            True if deleted successfully, False if not found
        """
        pass

    @abstractmethod
    def list_categories(self) -> List[str]:
        """
        List all available API categories.

        Returns:
            List of category names
        """
        pass

    @abstractmethod
    def list_versions(self, category: str) -> List[str]:
        """
        List all available API major versions for a category.

        Args:
            category: API category

        Returns:
            List of API major versions
        """
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """
        Check if the configuration source is available and accessible.

        Returns:
            True if source is available, False otherwise
        """
        pass

    @abstractmethod
    def get_source_info(self) -> Dict[str, Any]:
        """
        Get information about the configuration source.

        Returns:
            Dictionary with source metadata (type, location, version, etc.)
        """
        pass
