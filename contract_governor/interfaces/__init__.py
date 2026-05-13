"""
Abstract interfaces module implementing Dependency Inversion Principle.

This module defines abstract base classes that high-level modules depend on,
allowing low-level modules to implement these abstractions without creating
dependencies between concrete implementations.

The module also implements Interface Segregation Principle by providing
focused interfaces that separate concerns so clients only depend on
the specific capabilities they need.
"""

from .catalog_server import CatalogServer
from .configuration_source import ConfigurationSource
from .contract_linker import ContractLinker
from .contract_registry import ContractRegistry
from .documentation_renderer import DocumentationRenderer
from .serving_concerns import CatalogProvider, ContractProvider, HealthProvider
from .transformation_concerns import MetadataInjector, SecurityTransformer, URLTransformer
from .transformer import Transformer

# Focused interfaces implementing Interface Segregation Principle
from .validation_concerns import ContractStructureValidator, PolicyValidator, SecurityValidator
from .validator import Validator

__all__ = [
    # Core interfaces
    "CatalogServer",
    "ContractRegistry",
    "DocumentationRenderer",
    "ConfigurationSource",
    "ContractLinker",
    "Validator",
    "Transformer",
    # Validation concerns
    "ContractStructureValidator",
    "PolicyValidator",
    "SecurityValidator",
    # Transformation concerns
    "URLTransformer",
    "MetadataInjector",
    "SecurityTransformer",
    # Serving concerns
    "CatalogProvider",
    "ContractProvider",
    "HealthProvider",
]
