"""
Factory patterns for complex object creation.

Provides factory classes and functions for creating complex objects
with proper dependency injection and configuration.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, Type, TypeVar, cast

from .container import DIContainer

T = TypeVar('T')


class Factory(ABC):
    """
    Abstract factory interface for creating objects with dependency injection.

    Factories encapsulate complex object creation logic and ensure
    proper dependency injection for created objects.
    """

    @abstractmethod
    def create(self, **kwargs) -> Any:
        """
        Create an object instance.

        Args:
            **kwargs: Additional parameters for object creation

        Returns:
            Created object instance
        """
        pass


class ConfigurableFactory(Factory):
    """
    Factory that creates objects based on configuration.

    Uses dependency injection container to resolve dependencies
    and applies configuration-driven instantiation.
    """

    def __init__(self, container: DIContainer, config: Dict[str, Any]):
        """Initialize factory with a DI container and object-type configuration map."""
        self.container = container
        self.config = config

    def create(self, object_type: str, **kwargs) -> Any:  # type: ignore[override]  # Subclass requires object_type; base class has generic **kwargs signature
        """
        Create an object based on configuration.

        Args:
            object_type: Type of object to create (from configuration)
            **kwargs: Additional parameters

        Returns:
            Created object instance
        """
        if object_type not in self.config:
            raise ValueError(f"Unknown object type: {object_type}")

        type_config = self.config[object_type]
        class_path = type_config['class']

        # Import and resolve class
        module_name, class_name = class_path.rsplit('.', 1)
        module = __import__(module_name, fromlist=[class_name])
        cls = getattr(module, class_name)

        # Merge configuration parameters with kwargs
        params = {**type_config.get('parameters', {}), **kwargs}

        # Create instance with dependency injection
        return self._create_with_injection(cls, params)

    def _create_with_injection(self, cls: Type[T], params: Dict[str, Any]) -> T:
        """Create instance with dependency injection and parameters."""
        # This would integrate with the DI container to resolve dependencies
        # and apply the provided parameters
        return cls(**params)


class ServiceFactory:
    """
    Factory for creating services with proper dependency injection.

    Provides convenient methods for creating commonly used services
    with their dependencies properly injected.
    """

    def __init__(self, container: DIContainer):
        """Initialize service factory with a DI container for dependency resolution."""
        self.container = container

    def create_validation_pipeline(self, stipulation_config: Dict[str, Any]) -> Any:
        """
        Create a validation pipeline with appropriate validators.

        Args:
            stipulation_config: Stipulation configuration

        Returns:
            Configured validation pipeline
        """
        from ..validation.pipeline import ValidationPipeline

        # Resolve all registered validators
        _validators: list[Any] = []
        # This would be implemented to discover and instantiate validators
        # based on the stipulation configuration

        # Safe: callers pass StipulationConfig at runtime; Dict[str, Any] is the declared param type for flexibility
        return ValidationPipeline(cast(Any, stipulation_config))

    def create_transformation_pipeline(self, stipulation_config: Dict[str, Any]) -> Any:
        """
        Create a transformation pipeline with appropriate transformers.

        Args:
            stipulation_config: Stipulation configuration

        Returns:
            Configured transformation pipeline
        """
        from ..transformation.pipeline import TransformationPipeline

        # Resolve all registered transformers
        _transformers: list[Any] = []
        # This would be implemented to discover and instantiate transformers
        # based on the stipulation configuration

        # Safe: callers pass StipulationConfig at runtime; Dict[str, Any] is the declared param type for flexibility
        return TransformationPipeline(cast(Any, stipulation_config))

    def create_catalog_server(self, framework: str, **kwargs) -> Any:
        """
        Create a catalog server for the specified framework.

        Args:
            framework: Framework name (fastapi, flask, django)
            **kwargs: Framework-specific parameters

        Returns:
            Configured catalog server
        """
        from ..interfaces.catalog_server import CatalogServer

        # Resolve catalog server implementation for the framework
        # Safe: container resolves to a concrete implementation registered at runtime
        return self.container.resolve(CatalogServer, name=framework)  # type: ignore[type-abstract]  # CatalogServer is abstract but container resolves concrete impl


def create_factory_from_config(container: DIContainer, config_path: str) -> ConfigurableFactory:
    """
    Create a factory from configuration file.

    Args:
        container: Dependency injection container
        config_path: Path to configuration file

    Returns:
        Configured factory instance
    """
    import json
    from pathlib import Path

    import yaml

    config_file = Path(config_path)

    if config_file.suffix.lower() == '.json':
        with open(config_file, 'r') as f:
            config = json.load(f)
    elif config_file.suffix.lower() in ['.yml', '.yaml']:
        with open(config_file, 'r') as f:
            config = yaml.safe_load(f)
    else:
        raise ValueError(f"Unsupported configuration file format: {config_file.suffix}")

    return ConfigurableFactory(container, config)
