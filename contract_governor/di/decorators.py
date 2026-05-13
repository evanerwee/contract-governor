"""
Decorators for dependency injection.

Provides decorators to mark classes as injectable and to inject dependencies
automatically, supporting the Dependency Inversion Principle.
"""

import inspect
from functools import wraps
from typing import Any, Dict, Optional, Type, TypeVar

T = TypeVar("T")

# Global registry for injectable classes
_injectable_classes: Dict[Type, Dict[str, Any]] = {}


def injectable(
    interface: Optional[Type] = None, scope: str = "singleton", name: Optional[str] = None, tags: Optional[list] = None
):
    """
    Decorator to mark a class as injectable.

    Args:
        interface: Interface this class implements
        scope: Service scope (singleton or transient)
        name: Optional service name
        tags: Optional tags for service discovery
    """

    def decorator(cls: Type[T]) -> Type[T]:
        """Register the class as injectable and attach metadata."""
        # Store injectable metadata
        _injectable_classes[cls] = {"interface": interface or cls, "scope": scope, "name": name, "tags": tags or []}

        # Add metadata to class
        setattr(cls, "_injectable_metadata", _injectable_classes[cls])

        return cls

    return decorator


def inject(container_attr: str = "_container"):
    """
    Decorator to inject dependencies into method parameters.

    Args:
        container_attr: Attribute name where DI container is stored
    """

    def decorator(func):
        """Wrap the method to resolve dependencies from the DI container before invocation."""

        @wraps(func)
        def wrapper(self, *args, **kwargs):
            """Resolve unbound parameters from the DI container and call the original method."""
            # Get the DI container from the instance
            container = getattr(self, container_attr, None)
            if not container:
                raise ValueError(f"No DI container found at {container_attr}")

            # Get function signature
            signature = inspect.signature(func)
            parameters = signature.parameters

            # Skip 'self' parameter
            param_names = [name for name in parameters.keys() if name != "self"]

            # Resolve dependencies for parameters not provided in kwargs
            for param_name in param_names:
                if param_name not in kwargs:
                    param = parameters[param_name]

                    if param.annotation != inspect.Parameter.empty:
                        try:
                            kwargs[param_name] = container.resolve(param.annotation)
                        except ValueError:
                            if param.default == inspect.Parameter.empty:
                                raise ValueError(f"Cannot resolve dependency {param.annotation}")

            return func(self, *args, **kwargs)

        return wrapper

    return decorator


def auto_wire(container_attr: str = "_container"):
    """
    Class decorator to automatically wire dependencies in __init__.

    Args:
        container_attr: Attribute name where DI container is stored
    """

    def decorator(cls: Type[T]) -> Type[T]:
        """Replace the class __init__ with a version that auto-resolves dependencies."""
        original_init = cls.__init__

        @wraps(original_init)
        def new_init(self, *args, **kwargs):
            """Auto-wire dependencies from the DI container before calling the original __init__."""
            # Store container reference
            if "container" in kwargs:
                setattr(self, container_attr, kwargs.pop("container"))

            # Get original __init__ signature
            signature = inspect.signature(original_init)
            parameters = signature.parameters

            # Skip 'self' parameter
            param_names = [name for name in parameters.keys() if name != "self"]

            # Get container
            container = getattr(self, container_attr, None)

            if container:
                # Resolve dependencies for parameters not provided
                for param_name in param_names:
                    if param_name not in kwargs:
                        param = parameters[param_name]

                        if param.annotation != inspect.Parameter.empty:
                            try:
                                kwargs[param_name] = container.resolve(param.annotation)
                            except ValueError:
                                if param.default == inspect.Parameter.empty:
                                    raise ValueError(f"Cannot resolve dependency {param.annotation}")

            # Call original __init__
            original_init(self, *args, **kwargs)

        setattr(cls, "__init__", new_init)
        return cls

    return decorator


def get_injectable_classes() -> Dict[Type, Dict[str, Any]]:
    """
    Get all classes marked as injectable.

    Returns:
        Dictionary mapping classes to their injectable metadata
    """
    return _injectable_classes.copy()


def is_injectable(cls: Type) -> bool:
    """
    Check if a class is marked as injectable.

    Args:
        cls: Class to check

    Returns:
        True if class is injectable, False otherwise
    """
    return cls in _injectable_classes


def get_injectable_metadata(cls: Type) -> Optional[Dict[str, Any]]:
    """
    Get injectable metadata for a class.

    Args:
        cls: Class to get metadata for

    Returns:
        Injectable metadata if class is injectable, None otherwise
    """
    return _injectable_classes.get(cls)
