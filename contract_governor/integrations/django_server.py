"""
Django catalog server implementation following SOLID principles.

This implementation demonstrates how Django can be integrated using
the same interfaces while maintaining framework-specific patterns.
"""

import os
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from django.http import HttpResponse, JsonResponse
from django.urls import include, path
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt

from ..core.models import ExposedContractRecord
from ..interfaces.catalog_server import CatalogServer
from ..interfaces.documentation_renderer import DocumentationRenderer
from ..interfaces.serving_concerns import CatalogProvider, ContractProvider, HealthProvider


class DjangoCatalogServer(CatalogServer):
    """
    Django implementation of catalog server following SOLID principles.

    This demonstrates how Django's class-based views can be integrated
    while maintaining the same interface contract.
    """

    def __init__(
        self,
        catalog_provider: CatalogProvider,
        contract_provider: ContractProvider,
        health_provider: HealthProvider,
        documentation_renderer: Optional[DocumentationRenderer] = None
    ):
        """
        Initialize Django catalog server with injected dependencies.

        Args:
            catalog_provider: Provider for catalog data
            contract_provider: Provider for individual contracts
            health_provider: Provider for health checks
            documentation_renderer: Optional documentation renderer
        """
        self.catalog_provider = catalog_provider
        self.contract_provider = contract_provider
        self.health_provider = health_provider
        self.documentation_renderer = documentation_renderer
        self.url_patterns: list[Any] = []

    def register_catalog_endpoint(self, url_path: str = "api-catalog/", handler: Callable[..., Any] | None = None) -> None:
        """Register Django URL patterns for API catalog."""

        class CatalogView(View):
            """View that serves the API catalog listing with optional filtering."""
            def __init__(self, server_instance):
                """Initialize with a reference to the parent DjangoCatalogServer."""
                super().__init__()
                self.server = server_instance

            @method_decorator(csrf_exempt)
            def dispatch(self, request, *args, **kwargs):
                """Dispatch requests with CSRF exemption for API access."""
                return super().dispatch(request, *args, **kwargs)

            def get(self, request):
                """Get API catalog with optional filtering."""
                try:
                    # Extract query parameters
                    api_major = request.GET.get('api_major')
                    category = request.GET.get('category')
                    visible_only = request.GET.get('visible_only', 'true').lower() == 'true'

                    # Build filters
                    filters = {}
                    if api_major:
                        filters["api_major_version"] = api_major
                    if category:
                        filters["category"] = category

                    # Delegate to catalog provider
                    contracts = self.server.catalog_provider.get_catalog_contracts(filters)

                    # Apply visibility filter
                    if visible_only:
                        contracts = self.server.catalog_provider.filter_visible_contracts(contracts)

                    # Build response
                    catalog_response = {
                        "contracts": [self.server._contract_to_summary(contract) for contract in contracts],
                        "total": len(contracts),
                        "filters": {
                            "api_major": api_major,
                            "category": category,
                            "visible_only": visible_only
                        },
                        "generated_at": datetime.now(timezone.utc).isoformat()
                    }

                    return JsonResponse(catalog_response)

                except Exception as e:
                    return JsonResponse({"error": f"Failed to retrieve catalog: {str(e)}"}, status=500)

        class CatalogDocsView(View):
            """View that renders the HTML documentation page for the API catalog."""
            def __init__(self, server_instance):
                """Initialize with a reference to the parent DjangoCatalogServer."""
                super().__init__()
                self.server = server_instance

            def get(self, request):
                """Get catalog documentation page."""
                if not self.server.documentation_renderer:
                    return JsonResponse({"error": "Documentation renderer not available"}, status=404)

                try:
                    contracts = self.server.catalog_provider.get_catalog_contracts()
                    visible_contracts = self.server.catalog_provider.filter_visible_contracts(contracts)

                    contract_summaries = [self.server._contract_to_summary(c) for c in visible_contracts]
                    html_content = self.server.documentation_renderer.render_catalog_page(contract_summaries)

                    return HttpResponse(html_content, content_type='text/html')

                except Exception as e:
                    return JsonResponse({"error": f"Failed to render catalog docs: {str(e)}"}, status=500)

        # Add URL patterns
        catalog_patterns = [
            path('', CatalogView.as_view(server_instance=self), name='catalog'),
        ]

        if self.documentation_renderer:
            catalog_patterns.append(
                path('docs/', CatalogDocsView.as_view(server_instance=self), name='catalog_docs')
            )

        self.url_patterns.append(path(url_path, include(catalog_patterns)))

    def register_contract_endpoint(self, url_path: str = "contracts/<str:category>/<str:api_major>/", handler: Callable[..., Any] | None = None) -> None:
        """Register Django URL patterns for individual contracts."""

        class ContractSpecView(View):
            """View that serves the OpenAPI specification for a specific contract."""
            def __init__(self, server_instance):
                """Initialize with a reference to the parent DjangoCatalogServer."""
                super().__init__()
                self.server = server_instance

            def get(self, request, category, api_major):
                """Get OpenAPI specification for a specific contract."""
                try:
                    if not self.server.contract_provider.is_contract_available(category, api_major):
                        return JsonResponse({"error": f"Contract not found: {category}:{api_major}"}, status=404)

                    spec = self.server.contract_provider.get_contract_spec(category, api_major)
                    if not spec:
                        return JsonResponse({"error": f"Contract specification not available: {category}:{api_major}"}, status=404)

                    return JsonResponse(spec)

                except Exception as e:
                    return JsonResponse({"error": f"Failed to retrieve contract: {str(e)}"}, status=500)

        class ContractMetadataView(View):
            """View that serves metadata for a specific contract."""
            def __init__(self, server_instance):
                """Initialize with a reference to the parent DjangoCatalogServer."""
                super().__init__()
                self.server = server_instance

            def get(self, request, category, api_major):
                """Get metadata for a specific contract."""
                try:
                    metadata = self.server.contract_provider.get_contract_metadata(category, api_major)
                    if not metadata:
                        return JsonResponse({"error": f"Contract metadata not found: {category}:{api_major}"}, status=404)

                    return JsonResponse(metadata)

                except Exception as e:
                    return JsonResponse({"error": f"Failed to retrieve metadata: {str(e)}"}, status=500)

        class ContractDocsView(View):
            """View that renders the HTML documentation page for a specific contract."""
            def __init__(self, server_instance):
                """Initialize with a reference to the parent DjangoCatalogServer."""
                super().__init__()
                self.server = server_instance

            def get(self, request, category, api_major):
                """Get documentation page for a specific contract."""
                if not self.server.documentation_renderer:
                    return JsonResponse({"error": "Documentation renderer not available"}, status=404)

                try:
                    if not self.server.contract_provider.is_contract_available(category, api_major):
                        return JsonResponse({"error": f"Contract not found: {category}:{api_major}"}, status=404)

                    from html import escape as html_escape
                    safe_category = html_escape(category)
                    safe_api_major = html_escape(api_major)
                    contract_url = f"/contracts/{safe_category}/{safe_api_major}/openapi.json"
                    title = f"{safe_category} {safe_api_major} API Documentation"

                    html_content = self.server.documentation_renderer.render_contract_page(contract_url, title)
                    return HttpResponse(html_content, content_type='text/html')

                except Exception as e:
                    return JsonResponse({"error": f"Failed to render contract docs: {str(e)}"}, status=500)

        # Add URL patterns
        contract_patterns = [
            path('openapi.json', ContractSpecView.as_view(server_instance=self), name='contract_spec'),
            path('metadata', ContractMetadataView.as_view(server_instance=self), name='contract_metadata'),
        ]

        if self.documentation_renderer:
            contract_patterns.append(
                path('docs/', ContractDocsView.as_view(server_instance=self), name='contract_docs')
            )

        self.url_patterns.append(path(url_path, include(contract_patterns)))

    def serve_openapi_spec(self, spec: dict, url_path: str) -> None:
        """Serve an OpenAPI specification at a custom path."""

        class CustomSpecView(View):
            """View that serves a custom OpenAPI specification at a given path."""
            def __init__(self, spec_data):
                """Initialize with the OpenAPI spec data to serve."""
                super().__init__()
                self.spec = spec_data

            def get(self, request):
                """Serve custom OpenAPI specification."""
                return JsonResponse(self.spec)

        self.url_patterns.append(path(url_path, CustomSpecView.as_view(spec_data=spec)))

    def register_health_endpoints(self) -> None:
        """Register health check endpoints."""

        class HealthView(View):
            """View that provides a liveness health check endpoint."""
            def __init__(self, server_instance):
                """Initialize with a reference to the parent DjangoCatalogServer."""
                super().__init__()
                self.server = server_instance

            def get(self, request):
                """Liveness probe."""
                try:
                    health_status = self.server.health_provider.check_health()
                    status_code = 200 if health_status.get("status") == "healthy" else 503
                    return JsonResponse(health_status, status=status_code)
                except Exception as e:
                    return JsonResponse({"status": "unhealthy", "error": str(e)}, status=503)

        class ReadyView(View):
            """View that provides a readiness probe endpoint."""
            def __init__(self, server_instance):
                """Initialize with a reference to the parent DjangoCatalogServer."""
                super().__init__()
                self.server = server_instance

            def get(self, request):
                """Readiness probe."""
                try:
                    readiness_status = self.server.health_provider.check_readiness()
                    status_code = 200 if readiness_status.get("status") == "ready" else 503
                    return JsonResponse(readiness_status, status=status_code)
                except Exception as e:
                    return JsonResponse({"status": "not_ready", "error": str(e)}, status=503)

        class InfoView(View):
            """View that provides service information metadata."""
            def __init__(self, server_instance):
                """Initialize with a reference to the parent DjangoCatalogServer."""
                super().__init__()
                self.server = server_instance

            def get(self, request):
                """Service information endpoint."""
                try:
                    return JsonResponse(self.server.health_provider.get_service_info())
                except Exception as e:
                    return JsonResponse({"error": f"Failed to get service info: {str(e)}"}, status=500)

        # Add health URL patterns
        health_patterns = [
            path('health/', HealthView.as_view(server_instance=self), name='health'),
            path('ready/', ReadyView.as_view(server_instance=self), name='ready'),
            path('info/', InfoView.as_view(server_instance=self), name='info'),
        ]

        self.url_patterns.extend(health_patterns)

    def get_exposed_contracts(self, filters: Optional[dict] = None) -> List[ExposedContractRecord]:
        """Retrieve exposed contracts with optional filtering."""
        return self.catalog_provider.get_catalog_contracts(filters)

    def get_url_patterns(self) -> List:
        """Get Django URL patterns for inclusion in main URLconf."""
        return self.url_patterns

    def _contract_to_summary(self, contract: ExposedContractRecord) -> Dict[str, Any]:
        """Convert ExposedContractRecord to summary format."""
        return {
            "category": contract.category,
            "api_major_version": contract.api_major_version,
            "contract_version": contract.contract_version,
            "title": contract.exposed_openapi_spec.get("info", {}).get("title", "Unknown API"),
            "description": contract.exposed_openapi_spec.get("info", {}).get("description", ""),
            "openapi_url": contract.openapi_mount_path,
            "docs_url": f"/contracts/{contract.category}/{contract.api_major_version}/docs",
            "proxy_prefix": contract.proxy_prefix,
            "source_service": contract.source_service,
            "exposed_at": contract.exposed_at.isoformat() if contract.exposed_at else None,
            "stipulation_applied": contract.stipulation_applied
        }


class DjangoAppFactory:
    """Factory for creating Django URL configurations with dependency injection."""

    @staticmethod
    def create_catalog_urls(
        catalog_provider: CatalogProvider,
        contract_provider: ContractProvider,
        health_provider: HealthProvider,
        documentation_renderer: Optional[DocumentationRenderer] = None
    ) -> List:
        """
        Create Django URL patterns configured for catalog serving.

        Args:
            catalog_provider: Provider for catalog data
            contract_provider: Provider for individual contracts
            health_provider: Provider for health checks
            documentation_renderer: Optional documentation renderer

        Returns:
            List of Django URL patterns
        """
        # Create catalog server with dependency injection
        catalog_server = DjangoCatalogServer(
            catalog_provider=catalog_provider,
            contract_provider=contract_provider,
            health_provider=health_provider,
            documentation_renderer=documentation_renderer
        )

        # Register all endpoints
        catalog_server.register_health_endpoints()
        catalog_server.register_catalog_endpoint()
        catalog_server.register_contract_endpoint()

        return catalog_server.get_url_patterns()


# Example Django settings configuration
DJANGO_CATALOG_SETTINGS = {
    'INSTALLED_APPS': [
        'django.contrib.contenttypes',
        'django.contrib.auth',
        'contract_stipulations.integrations.django_server',
    ],
    'MIDDLEWARE': [
        'django.middleware.security.SecurityMiddleware',
        'django.middleware.common.CommonMiddleware',
        'django.middleware.csrf.CsrfViewMiddleware',
    ],
    'ROOT_URLCONF': 'contract_stipulations.integrations.django_urls',
    'SECRET_KEY': os.environ.get('DJANGO_SECRET_KEY', ''),
    'DEBUG': False,
    'ALLOWED_HOSTS': ['*'],
}
