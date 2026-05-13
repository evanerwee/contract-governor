"""
Framework integrations for Contract Stipulations system.

This module provides web framework integrations following SOLID principles,
allowing the stipulations system to work with multiple frameworks while
maintaining consistent behavior and extensibility.
"""

from .framework_registry import (
    CatalogServerFactory,
    FrameworkAdapter,
    FrameworkRegistry,
    FrameworkType,
    framework_registry,
)
from .scalar_renderer import (
    DocumentationRendererRegistry,
    ScalarDocumentationRenderer,
    SwaggerUIRenderer,
    documentation_registry,
)

# Framework-specific imports (optional dependencies)
try:
    from .fastapi_server import FastAPIAppFactory, FastAPICatalogServer
    FASTAPI_AVAILABLE = True
except ImportError:
    FASTAPI_AVAILABLE = False

try:
    from .flask_server import FlaskAppFactory, FlaskCatalogServer
    FLASK_AVAILABLE = True
except ImportError:
    FLASK_AVAILABLE = False

try:
    from .django_server import DjangoAppFactory, DjangoCatalogServer
    DJANGO_AVAILABLE = True
except ImportError:
    DJANGO_AVAILABLE = False

__all__ = [
    # Core framework integration
    'FrameworkRegistry',
    'FrameworkAdapter',
    'FrameworkType',
    'CatalogServerFactory',
    'framework_registry',

    # Documentation rendering
    'ScalarDocumentationRenderer',
    'DocumentationRendererRegistry',
    'SwaggerUIRenderer',
    'documentation_registry',

    # Availability flags
    'FASTAPI_AVAILABLE',
    'FLASK_AVAILABLE',
    'DJANGO_AVAILABLE',
]

# Conditionally add framework-specific exports
if FASTAPI_AVAILABLE:
    __all__.extend(['FastAPICatalogServer', 'FastAPIAppFactory'])

if FLASK_AVAILABLE:
    __all__.extend(['FlaskCatalogServer', 'FlaskAppFactory'])

if DJANGO_AVAILABLE:
    __all__.extend(['DjangoCatalogServer', 'DjangoAppFactory'])
