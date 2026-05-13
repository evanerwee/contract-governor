"""
Dependency Injection framework for loose coupling and testability.

This module implements a lightweight dependency injection container that
supports configuration-driven object instantiation and factory patterns
for complex object creation.
"""

from .container import DIContainer, Scope
from .decorators import auto_wire, inject, injectable
from .factory import ConfigurableFactory, Factory, ServiceFactory
from .registry import ServiceRegistration, ServiceRegistry, ServiceStatus
from .setup import DISetup, create_default_setup

__all__ = [
    "DIContainer",
    "Scope",
    "Factory",
    "ServiceFactory",
    "ConfigurableFactory",
    "ServiceRegistry",
    "ServiceRegistration",
    "ServiceStatus",
    "injectable",
    "inject",
    "auto_wire",
    "DISetup",
    "create_default_setup"
]
