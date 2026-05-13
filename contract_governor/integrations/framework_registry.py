"""
Framework registry and plugin system for extensible web framework integration.

This module implements the Factory pattern and plugin architecture to allow
new framework adapters to be added without modifying existing code.
"""

from abc import ABC, abstractmethod
from enum import Enum
from typing import Any, Dict, List, Optional

from ..interfaces.catalog_server import CatalogServer
from ..interfaces.documentation_renderer import DocumentationRenderer
from ..interfaces.serving_concerns import CatalogProvider, ContractProvider, HealthProvider


class FrameworkType(Enum):
    """Enumeration of supported web framework types."""

    FASTAPI = "fastapi"
    FLASK = "flask"
    DJANGO = "django"
    STARLETTE = "starlette"
    TORNADO = "tornado"
    AIOHTTP = "aiohttp"


class FrameworkAdapter(ABC):
    """
    Abstract base class for framework adapters.

    This interface ensures all framework adapters follow the same pattern
    while allowing framework-specific implementations.
    """

    @abstractmethod
    def create_catalog_server(
        self,
        catalog_provider: CatalogProvider,
        contract_provider: ContractProvider,
        health_provider: HealthProvider,
        documentation_renderer: Optional[DocumentationRenderer] = None,
        **kwargs,
    ) -> CatalogServer:
        """
        Create a catalog server instance for this framework.

        Args:
            catalog_provider: Provider for catalog data
            contract_provider: Provider for individual contracts
            health_provider: Provider for health checks
            documentation_renderer: Optional documentation renderer
            **kwargs: Framework-specific configuration options

        Returns:
            CatalogServer instance for this framework
        """
        pass

    @abstractmethod
    def create_application(
        self,
        catalog_provider: CatalogProvider,
        contract_provider: ContractProvider,
        health_provider: HealthProvider,
        documentation_renderer: Optional[DocumentationRenderer] = None,
        **kwargs,
    ) -> Any:
        """
        Create a complete application instance for this framework.

        Args:
            catalog_provider: Provider for catalog data
            contract_provider: Provider for individual contracts
            health_provider: Provider for health checks
            documentation_renderer: Optional documentation renderer
            **kwargs: Framework-specific configuration options

        Returns:
            Framework-specific application instance
        """
        pass

    @abstractmethod
    def get_framework_type(self) -> FrameworkType:
        """Get the framework type this adapter supports."""
        pass

    @abstractmethod
    def get_required_dependencies(self) -> List[str]:
        """Get list of required Python packages for this framework."""
        pass

    @abstractmethod
    def validate_configuration(self, config: Dict[str, Any]) -> List[str]:
        """
        Validate framework-specific configuration.

        Args:
            config: Configuration dictionary

        Returns:
            List of validation error messages (empty if valid)
        """
        pass


class FastAPIAdapter(FrameworkAdapter):
    """FastAPI framework adapter."""

    def create_catalog_server(
        self,
        catalog_provider: CatalogProvider,
        contract_provider: ContractProvider,
        health_provider: HealthProvider,
        documentation_renderer: Optional[DocumentationRenderer] = None,
        **kwargs,
    ) -> CatalogServer:
        """Create FastAPI catalog server."""
        from .fastapi_server import FastAPICatalogServer

        # Import FastAPI here to avoid hard dependency
        try:
            from fastapi import FastAPI
        except ImportError:
            raise ImportError("FastAPI is required for FastAPIAdapter. Install with: pip install fastapi")

        app = kwargs.get("app") or FastAPI(
            title=kwargs.get("title", "API Contract Catalog"),
            description=kwargs.get("description", "Centralized catalog of governed API contracts"),
            version=kwargs.get("version", "1.0.0"),
        )

        return FastAPICatalogServer(
            app=app,
            catalog_provider=catalog_provider,
            contract_provider=contract_provider,
            health_provider=health_provider,
            documentation_renderer=documentation_renderer,
        )

    def create_application(
        self,
        catalog_provider: CatalogProvider,
        contract_provider: ContractProvider,
        health_provider: HealthProvider,
        documentation_renderer: Optional[DocumentationRenderer] = None,
        **kwargs,
    ) -> Any:
        """Create complete FastAPI application."""
        from .fastapi_server import FastAPIAppFactory

        return FastAPIAppFactory.create_catalog_app(
            catalog_provider=catalog_provider,
            contract_provider=contract_provider,
            health_provider=health_provider,
            documentation_renderer=documentation_renderer,
            title=kwargs.get("title", "API Contract Catalog"),
            description=kwargs.get("description", "Centralized catalog of governed API contracts"),
            version=kwargs.get("version", "1.0.0"),
        )

    def get_framework_type(self) -> FrameworkType:
        """Get framework type."""
        return FrameworkType.FASTAPI

    def get_required_dependencies(self) -> List[str]:
        """Get required dependencies."""
        return ["fastapi", "uvicorn"]

    def validate_configuration(self, config: Dict[str, Any]) -> List[str]:
        """Validate FastAPI configuration."""
        errors = []

        # Validate optional configuration
        if "title" in config and not isinstance(config["title"], str):
            errors.append("FastAPI 'title' must be a string")

        if "version" in config and not isinstance(config["version"], str):
            errors.append("FastAPI 'version' must be a string")

        return errors


class FlaskAdapter(FrameworkAdapter):
    """Flask framework adapter."""

    def create_catalog_server(
        self,
        catalog_provider: CatalogProvider,
        contract_provider: ContractProvider,
        health_provider: HealthProvider,
        documentation_renderer: Optional[DocumentationRenderer] = None,
        **kwargs,
    ) -> CatalogServer:
        """Create Flask catalog server."""
        from .flask_server import FlaskCatalogServer

        try:
            from flask import Flask
        except ImportError:
            raise ImportError("Flask is required for FlaskAdapter. Install with: pip install flask")

        app = kwargs.get("app") or Flask(kwargs.get("app_name", "catalog_app"))

        return FlaskCatalogServer(
            app=app,
            catalog_provider=catalog_provider,
            contract_provider=contract_provider,
            health_provider=health_provider,
            documentation_renderer=documentation_renderer,
        )

    def create_application(
        self,
        catalog_provider: CatalogProvider,
        contract_provider: ContractProvider,
        health_provider: HealthProvider,
        documentation_renderer: Optional[DocumentationRenderer] = None,
        **kwargs,
    ) -> Any:
        """Create complete Flask application."""
        from .flask_server import FlaskAppFactory

        return FlaskAppFactory.create_catalog_app(
            catalog_provider=catalog_provider,
            contract_provider=contract_provider,
            health_provider=health_provider,
            documentation_renderer=documentation_renderer,
            app_name=kwargs.get("app_name", "catalog_app"),
        )

    def get_framework_type(self) -> FrameworkType:
        """Get framework type."""
        return FrameworkType.FLASK

    def get_required_dependencies(self) -> List[str]:
        """Get required dependencies."""
        return ["flask"]

    def validate_configuration(self, config: Dict[str, Any]) -> List[str]:
        """Validate Flask configuration."""
        errors = []

        if "app_name" in config and not isinstance(config["app_name"], str):
            errors.append("Flask 'app_name' must be a string")

        return errors


class DjangoAdapter(FrameworkAdapter):
    """Django framework adapter."""

    def create_catalog_server(
        self,
        catalog_provider: CatalogProvider,
        contract_provider: ContractProvider,
        health_provider: HealthProvider,
        documentation_renderer: Optional[DocumentationRenderer] = None,
        **kwargs,
    ) -> CatalogServer:
        """Create Django catalog server."""
        from .django_server import DjangoCatalogServer

        try:
            import django
        except ImportError:
            raise ImportError("Django is required for DjangoAdapter. Install with: pip install django")

        return DjangoCatalogServer(
            catalog_provider=catalog_provider,
            contract_provider=contract_provider,
            health_provider=health_provider,
            documentation_renderer=documentation_renderer,
        )

    def create_application(
        self,
        catalog_provider: CatalogProvider,
        contract_provider: ContractProvider,
        health_provider: HealthProvider,
        documentation_renderer: Optional[DocumentationRenderer] = None,
        **kwargs,
    ) -> Any:
        """Create Django URL patterns."""
        from .django_server import DjangoAppFactory

        return DjangoAppFactory.create_catalog_urls(
            catalog_provider=catalog_provider,
            contract_provider=contract_provider,
            health_provider=health_provider,
            documentation_renderer=documentation_renderer,
        )

    def get_framework_type(self) -> FrameworkType:
        """Get framework type."""
        return FrameworkType.DJANGO

    def get_required_dependencies(self) -> List[str]:
        """Get required dependencies."""
        return ["django"]

    def validate_configuration(self, config: Dict[str, Any]) -> List[str]:
        """Validate Django configuration."""
        errors: list[str] = []

        # Django-specific validation could go here
        return errors


class FrameworkRegistry:
    """
    Registry for framework adapters implementing plugin architecture.

    This allows adding new framework adapters without modifying existing code,
    following the Open/Closed Principle.
    """

    def __init__(self):
        """Initialize the framework registry."""
        self._adapters: Dict[FrameworkType, FrameworkAdapter] = {}
        self._default_framework = FrameworkType.FASTAPI

        # Register built-in adapters
        self.register_adapter(FastAPIAdapter())
        self.register_adapter(FlaskAdapter())
        self.register_adapter(DjangoAdapter())

    def register_adapter(self, adapter: FrameworkAdapter) -> None:
        """
        Register a new framework adapter.

        Args:
            adapter: FrameworkAdapter instance
        """
        if not isinstance(adapter, FrameworkAdapter):
            raise ValueError("Adapter must implement FrameworkAdapter interface")

        framework_type = adapter.get_framework_type()
        self._adapters[framework_type] = adapter

    def get_adapter(self, framework_type: FrameworkType) -> FrameworkAdapter:
        """
        Get a framework adapter by type.

        Args:
            framework_type: Type of framework adapter to retrieve

        Returns:
            FrameworkAdapter instance

        Raises:
            ValueError: If framework type is not registered
        """
        if framework_type not in self._adapters:
            raise ValueError(f"Unknown framework type: {framework_type}. Available: {list(self._adapters.keys())}")

        return self._adapters[framework_type]

    def list_frameworks(self) -> List[FrameworkType]:
        """
        List all registered framework types.

        Returns:
            List of registered framework types
        """
        return list(self._adapters.keys())

    def set_default_framework(self, framework_type: FrameworkType) -> None:
        """
        Set the default framework type.

        Args:
            framework_type: Framework type to set as default

        Raises:
            ValueError: If framework type is not registered
        """
        if framework_type not in self._adapters:
            raise ValueError(f"Cannot set unknown framework as default: {framework_type}")

        self._default_framework = framework_type

    def get_default_adapter(self) -> FrameworkAdapter:
        """
        Get the default framework adapter.

        Returns:
            Default FrameworkAdapter instance
        """
        return self.get_adapter(self._default_framework)

    def create_catalog_server(
        self,
        framework_type: FrameworkType,
        catalog_provider: CatalogProvider,
        contract_provider: ContractProvider,
        health_provider: HealthProvider,
        documentation_renderer: Optional[DocumentationRenderer] = None,
        **kwargs,
    ) -> CatalogServer:
        """
        Create a catalog server for the specified framework.

        Args:
            framework_type: Type of framework to use
            catalog_provider: Provider for catalog data
            contract_provider: Provider for individual contracts
            health_provider: Provider for health checks
            documentation_renderer: Optional documentation renderer
            **kwargs: Framework-specific configuration options

        Returns:
            CatalogServer instance
        """
        adapter = self.get_adapter(framework_type)
        return adapter.create_catalog_server(
            catalog_provider=catalog_provider,
            contract_provider=contract_provider,
            health_provider=health_provider,
            documentation_renderer=documentation_renderer,
            **kwargs,
        )

    def create_application(
        self,
        framework_type: FrameworkType,
        catalog_provider: CatalogProvider,
        contract_provider: ContractProvider,
        health_provider: HealthProvider,
        documentation_renderer: Optional[DocumentationRenderer] = None,
        **kwargs,
    ) -> Any:
        """
        Create a complete application for the specified framework.

        Args:
            framework_type: Type of framework to use
            catalog_provider: Provider for catalog data
            contract_provider: Provider for individual contracts
            health_provider: Provider for health checks
            documentation_renderer: Optional documentation renderer
            **kwargs: Framework-specific configuration options

        Returns:
            Framework-specific application instance
        """
        adapter = self.get_adapter(framework_type)
        return adapter.create_application(
            catalog_provider=catalog_provider,
            contract_provider=contract_provider,
            health_provider=health_provider,
            documentation_renderer=documentation_renderer,
            **kwargs,
        )

    def validate_framework_config(self, framework_type: FrameworkType, config: Dict[str, Any]) -> List[str]:
        """
        Validate configuration for a specific framework.

        Args:
            framework_type: Type of framework to validate for
            config: Configuration dictionary

        Returns:
            List of validation error messages
        """
        adapter = self.get_adapter(framework_type)
        return adapter.validate_configuration(config)

    def check_dependencies(self, framework_type: FrameworkType) -> Dict[str, bool]:
        """
        Check if required dependencies are available for a framework.

        Args:
            framework_type: Type of framework to check

        Returns:
            Dictionary mapping dependency names to availability status
        """
        adapter = self.get_adapter(framework_type)
        dependencies = adapter.get_required_dependencies()

        availability = {}
        for dep in dependencies:
            try:
                __import__(dep)
                availability[dep] = True
            except ImportError:
                availability[dep] = False

        return availability


# Global registry instance
framework_registry = FrameworkRegistry()


class CatalogServerFactory:
    """
    High-level factory for creating catalog servers with automatic framework detection.

    This provides a simplified interface for creating catalog servers without
    needing to know the specific framework adapter details.
    """

    @staticmethod
    def create_server(
        catalog_provider: CatalogProvider,
        contract_provider: ContractProvider,
        health_provider: HealthProvider,
        documentation_renderer: Optional[DocumentationRenderer] = None,
        framework: Optional[FrameworkType] = None,
        **kwargs,
    ) -> CatalogServer:
        """
        Create a catalog server with automatic framework detection.

        Args:
            catalog_provider: Provider for catalog data
            contract_provider: Provider for individual contracts
            health_provider: Provider for health checks
            documentation_renderer: Optional documentation renderer
            framework: Optional specific framework to use
            **kwargs: Framework-specific configuration options

        Returns:
            CatalogServer instance
        """
        if framework is None:
            framework = CatalogServerFactory._detect_framework()

        return framework_registry.create_catalog_server(
            framework_type=framework,
            catalog_provider=catalog_provider,
            contract_provider=contract_provider,
            health_provider=health_provider,
            documentation_renderer=documentation_renderer,
            **kwargs,
        )

    @staticmethod
    def create_application(
        catalog_provider: CatalogProvider,
        contract_provider: ContractProvider,
        health_provider: HealthProvider,
        documentation_renderer: Optional[DocumentationRenderer] = None,
        framework: Optional[FrameworkType] = None,
        **kwargs,
    ) -> Any:
        """
        Create a complete application with automatic framework detection.

        Args:
            catalog_provider: Provider for catalog data
            contract_provider: Provider for individual contracts
            health_provider: Provider for health checks
            documentation_renderer: Optional documentation renderer
            framework: Optional specific framework to use
            **kwargs: Framework-specific configuration options

        Returns:
            Framework-specific application instance
        """
        if framework is None:
            framework = CatalogServerFactory._detect_framework()

        return framework_registry.create_application(
            framework_type=framework,
            catalog_provider=catalog_provider,
            contract_provider=contract_provider,
            health_provider=health_provider,
            documentation_renderer=documentation_renderer,
            **kwargs,
        )

    @staticmethod
    def _detect_framework() -> FrameworkType:
        """
        Automatically detect the best available framework.

        Returns:
            FrameworkType for the detected framework
        """
        # Check for FastAPI first (preferred)
        try:
            import fastapi

            return FrameworkType.FASTAPI
        except ImportError:
            pass

        # Check for Flask
        try:
            import flask

            return FrameworkType.FLASK
        except ImportError:
            pass

        # Check for Django
        try:
            import django

            return FrameworkType.DJANGO
        except ImportError:
            pass

        # Default to FastAPI (will raise ImportError if not available)
        return FrameworkType.FASTAPI
