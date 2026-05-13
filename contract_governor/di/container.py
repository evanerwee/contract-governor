"""
Dependency Injection Container implementation.

Provides a lightweight container for managing dependencies and their lifecycles,
supporting singleton and transient scopes with configuration-driven instantiation.
"""

import inspect
from enum import Enum
from threading import Lock
from typing import Any, Callable, Dict, Optional, Type, TypeVar, Union, cast


class Scope(Enum):
    """Dependency scope enumeration."""

    SINGLETON = "singleton"
    TRANSIENT = "transient"


T = TypeVar("T")


class DIContainer:
    """
    Lightweight dependency injection container.

    Manages service registration, resolution, and lifecycle according to
    the Dependency Inversion Principle. Supports both singleton and transient
    scopes with automatic dependency resolution.
    """

    def __init__(self):
        """Initialize an empty DI container with service registry and instance cache."""
        self._services: Dict[str, Dict[str, Any]] = {}
        self._instances: Dict[str, Any] = {}
        self._lock = Lock()

    def register(
        self,
        interface: Type[T],
        implementation: Union[Type[T], Callable[[], T]],
        scope: Scope = Scope.SINGLETON,
        name: Optional[str] = None,
    ) -> None:
        """
        Register a service with the container.

        Args:
            interface: The interface or abstract base class
            implementation: The concrete implementation or factory function
            scope: Service scope (singleton or transient)
            name: Optional service name for multiple implementations
        """
        service_key = self._get_service_key(interface, name)

        with self._lock:
            self._services[service_key] = {
                "interface": interface,
                "implementation": implementation,
                "scope": scope,
                "name": name,
            }

    def register_instance(self, interface: Type[T], instance: T, name: Optional[str] = None) -> None:
        """
        Register a pre-created instance with the container.

        Args:
            interface: The interface or abstract base class
            instance: The pre-created instance
            name: Optional service name
        """
        service_key = self._get_service_key(interface, name)

        with self._lock:
            self._services[service_key] = {
                "interface": interface,
                "implementation": lambda: instance,
                "scope": Scope.SINGLETON,
                "name": name,
            }
            self._instances[service_key] = instance

    def resolve(self, interface: Type[T], name: Optional[str] = None) -> T:
        """
        Resolve a service from the container.

        Args:
            interface: The interface to resolve
            name: Optional service name

        Returns:
            Instance of the requested service

        Raises:
            ValueError: If service is not registered
        """
        service_key = self._get_service_key(interface, name)

        if service_key not in self._services:
            raise ValueError(f"Service {service_key} is not registered")

        service_config = self._services[service_key]

        # Return existing singleton instance if available
        if service_config["scope"] == Scope.SINGLETON and service_key in self._instances:
            # Safe cast: _instances stores objects registered as Type[T], so the
            # value at this key was originally provided as an instance of T.
            return cast(T, self._instances[service_key])

        # Create new instance
        instance = self._create_instance(service_config)

        # Store singleton instance
        if service_config["scope"] == Scope.SINGLETON:
            with self._lock:
                self._instances[service_key] = instance

        # Safe cast: _create_instance invokes the implementation registered for
        # Type[T], so the returned object is guaranteed to be an instance of T.
        return cast(T, instance)

    def is_registered(self, interface: Type[T], name: Optional[str] = None) -> bool:
        """
        Check if a service is registered.

        Args:
            interface: The interface to check
            name: Optional service name

        Returns:
            True if service is registered, False otherwise
        """
        service_key = self._get_service_key(interface, name)
        return service_key in self._services

    def clear(self) -> None:
        """Clear all registered services and instances."""
        with self._lock:
            self._services.clear()
            self._instances.clear()

    def _get_service_key(self, interface: Type[T], name: Optional[str]) -> str:
        """Generate a unique key for the service."""
        base_key = f"{interface.__module__}.{interface.__name__}"
        return f"{base_key}:{name}" if name else base_key

    def _create_instance(self, service_config: Dict[str, Any]) -> Any:
        """
        Create an instance of the service.

        Args:
            service_config: Service configuration dictionary

        Returns:
            New instance of the service
        """
        implementation = service_config["implementation"]

        # If implementation is a callable (factory function)
        if callable(implementation) and not inspect.isclass(implementation):
            return implementation()

        # If implementation is a class, resolve constructor dependencies
        if inspect.isclass(implementation):
            return self._create_class_instance(implementation)

        raise ValueError(f"Invalid implementation type: {type(implementation)}")

    def _create_class_instance(self, cls: Type[T]) -> T:
        """
        Create an instance of a class with dependency injection.

        Args:
            cls: The class to instantiate

        Returns:
            New instance with dependencies injected
        """
        # Get constructor signature
        signature = inspect.signature(cls.__init__)
        parameters = signature.parameters

        # Skip 'self' parameter
        param_names = [name for name in parameters.keys() if name != "self"]

        # Resolve dependencies
        kwargs = {}
        for param_name in param_names:
            param = parameters[param_name]

            # Skip parameters with default values if not registered
            if param.annotation != inspect.Parameter.empty:
                try:
                    kwargs[param_name] = self.resolve(param.annotation)
                except ValueError:
                    if param.default == inspect.Parameter.empty:
                        raise ValueError(f"Cannot resolve dependency {param.annotation} for {cls}")

        return cls(**kwargs)
