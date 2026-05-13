"""
Abstract interface for documentation rendering systems.

This interface implements the Dependency Inversion Principle by allowing
the catalog system to work with any documentation renderer (Scalar, Swagger UI,
ReDoc, etc.) without depending on specific implementations.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List


class DocumentationRenderer(ABC):
    """
    Abstract interface for rendering API documentation from OpenAPI specifications.

    This interface allows the system to support multiple documentation tools
    (Scalar, Swagger UI, ReDoc, etc.) through a common abstraction.
    """

    @abstractmethod
    def render_catalog_page(self, contracts: List[Dict[str, Any]]) -> str:
        """
        Render a catalog page showing multiple API contracts.

        Args:
            contracts: List of contract metadata dictionaries

        Returns:
            HTML string for the catalog page
        """
        pass

    @abstractmethod
    def render_contract_page(self, contract_url: str, title: str) -> str:
        """
        Render a documentation page for a single API contract.

        Args:
            contract_url: URL to the OpenAPI specification
            title: Title for the documentation page

        Returns:
            HTML string for the contract documentation page
        """
        pass

    @abstractmethod
    def get_renderer_config(self, contract_url: str) -> Dict[str, Any]:
        """
        Generate renderer-specific configuration for the given contract.

        Args:
            contract_url: URL to the OpenAPI specification

        Returns:
            Configuration dictionary for the documentation renderer
        """
        pass

    @abstractmethod
    def get_catalog_config(self, contracts: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Generate renderer-specific configuration for a multi-API catalog.

        Args:
            contracts: List of contract metadata dictionaries

        Returns:
            Configuration dictionary for the catalog renderer
        """
        pass

    @abstractmethod
    def supports_multi_api(self) -> bool:
        """
        Check if the renderer supports displaying multiple APIs in one view.

        Returns:
            True if multi-API display is supported, False otherwise
        """
        pass
