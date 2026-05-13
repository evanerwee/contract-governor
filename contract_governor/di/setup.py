"""
Configuration-driven dependency injection setup.

Provides utilities for setting up the dependency injection container
from configuration files and automatically registering services.
"""

import importlib
from pathlib import Path
from typing import Any, Dict, Optional, cast

from .container import DIContainer, Scope
from .decorators import get_injectable_classes
from .factory import ServiceFactory
from .registry import ServiceRegistry


class DISetup:
    """
    Configuration-driven dependency injection setup.

    Handles automatic service registration from configuration and
    discovery of injectable classes.
    """

    def __init__(self, container: Optional[DIContainer] = None):
        """Initialize DI setup with an optional container, registry, and factory."""
        self.container = container or DIContainer()
        self.registry = ServiceRegistry()
        self.factory = ServiceFactory(self.container)

    def setup_from_config(self, config: Dict[str, Any]) -> None:
        """
        Setup dependency injection from configuration.

        Args:
            config: Configuration dictionary with service definitions
        """
        # Register services from configuration
        services_config = config.get("services", {})
        for service_name, service_config in services_config.items():
            self._register_service_from_config(service_name, service_config)

        # Auto-discover and register injectable classes
        if config.get("auto_discover", True):
            self._auto_register_injectable_classes()

    def setup_from_file(self, config_path: str) -> None:
        """
        Setup dependency injection from configuration file.

        Args:
            config_path: Path to configuration file (JSON or YAML)
        """
        import json

        import yaml

        config_file = Path(config_path)

        if not config_file.exists():
            raise FileNotFoundError(f"Configuration file not found: {config_path}")

        if config_file.suffix.lower() == ".json":
            with open(config_file, "r") as f:
                config = json.load(f)
        elif config_file.suffix.lower() in [".yml", ".yaml"]:
            with open(config_file, "r") as f:
                config = yaml.safe_load(f)
        else:
            raise ValueError(f"Unsupported configuration file format: {config_file.suffix}")

        self.setup_from_config(config)

    def _register_service_from_config(self, service_name: str, service_config: Dict[str, Any]) -> None:
        """Register a service from configuration."""
        interface_path = service_config["interface"]
        implementation_path = service_config["implementation"]
        scope = Scope(service_config.get("scope", "singleton"))
        name = service_config.get("name")

        # Import interface and implementation
        interface = self._import_class(interface_path)
        implementation = self._import_class(implementation_path)

        # Register with container
        self.container.register(interface, implementation, scope, name)

        # Register with registry
        self.registry.register_service(
            interface=interface,
            implementation=implementation,
            name=name,
            scope=scope.value,
            metadata=service_config.get("metadata", {}),
            tags=service_config.get("tags", []),
        )

    def _auto_register_injectable_classes(self) -> None:
        """Auto-register classes marked with @injectable decorator."""
        injectable_classes = get_injectable_classes()

        for cls, metadata in injectable_classes.items():
            interface = metadata["interface"]
            scope = Scope(metadata["scope"])
            name = metadata["name"]
            tags = metadata["tags"]

            # Register with container
            self.container.register(interface, cls, scope, name)

            # Register with registry
            self.registry.register_service(
                interface=interface,
                implementation=cls,
                name=name,
                scope=scope.value,
                metadata={"auto_discovered": True},
                tags=tags,
            )

    def _import_class(self, class_path: str) -> type:
        """Import a class from its full path."""
        module_name, class_name = class_path.rsplit(".", 1)
        module = importlib.import_module(module_name)
        # Safe cast: getattr on a module returns the named attribute which is always a class
        # here, since callers only pass fully-qualified class paths (interface/implementation).
        return cast(type, getattr(module, class_name))

    def get_container(self) -> DIContainer:
        """Get the configured DI container."""
        return self.container

    def get_registry(self) -> ServiceRegistry:
        """Get the service registry."""
        return self.registry

    def get_factory(self) -> ServiceFactory:
        """Get the service factory."""
        return self.factory


def create_default_setup() -> DISetup:
    """
    Create a default dependency injection setup.

    Returns:
        Configured DISetup instance with default services
    """
    setup = DISetup()

    # Default configuration
    default_config = {
        "services": {
            # Core services would be defined here
        },
        "auto_discover": True,
    }

    setup.setup_from_config(default_config)
    return setup
