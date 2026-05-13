"""
Flask catalog server implementation following SOLID principles.

This implementation demonstrates how the same interfaces can be used
with different web frameworks while maintaining consistent behavior.
"""

from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from flask import Blueprint, Flask, Response, jsonify, request

from ..core.models import ExposedContractRecord
from ..interfaces.catalog_server import CatalogServer
from ..interfaces.documentation_renderer import DocumentationRenderer
from ..interfaces.serving_concerns import CatalogProvider, ContractProvider, HealthProvider


class FlaskCatalogServer(CatalogServer):
    """
    Flask implementation of catalog server following SOLID principles.

    This demonstrates Liskov Substitution Principle - it can replace
    FastAPICatalogServer without breaking the system behavior.
    """

    def __init__(
        self,
        app: Flask,
        catalog_provider: CatalogProvider,
        contract_provider: ContractProvider,
        health_provider: HealthProvider,
        documentation_renderer: Optional[DocumentationRenderer] = None
    ):
        """
        Initialize Flask catalog server with injected dependencies.

        Args:
            app: Flask application instance
            catalog_provider: Provider for catalog data
            contract_provider: Provider for individual contracts
            health_provider: Provider for health checks
            documentation_renderer: Optional documentation renderer
        """
        self.app = app
        self.catalog_provider = catalog_provider
        self.contract_provider = contract_provider
        self.health_provider = health_provider
        self.documentation_renderer = documentation_renderer

        # Create blueprint for catalog endpoints
        self.catalog_bp = Blueprint('catalog', __name__)
        self.contracts_bp = Blueprint('contracts', __name__)
        self.health_bp = Blueprint('health', __name__)

    def register_catalog_endpoint(self, path: str = "/api-catalog", handler: Callable[..., Any] | None = None) -> None:
        """Register Flask route for API catalog."""

        @self.catalog_bp.route(path, methods=['GET'])
        def get_api_catalog():
            """Get API catalog with optional filtering."""
            try:
                # Extract query parameters
                api_major = request.args.get('api_major')
                category = request.args.get('category')
                visible_only = request.args.get('visible_only', 'true').lower() == 'true'

                # Build filters
                filters = {}
                if api_major:
                    filters["api_major_version"] = api_major
                if category:
                    filters["category"] = category

                # Delegate to catalog provider
                contracts = self.catalog_provider.get_catalog_contracts(filters)

                # Apply visibility filter
                if visible_only:
                    contracts = self.catalog_provider.filter_visible_contracts(contracts)

                # Build response
                catalog_response = {
                    "contracts": [self._contract_to_summary(contract) for contract in contracts],
                    "total": len(contracts),
                    "filters": {
                        "api_major": api_major,
                        "category": category,
                        "visible_only": visible_only
                    },
                    "generated_at": datetime.now(timezone.utc).isoformat()
                }

                return jsonify(catalog_response)

            except Exception as e:
                return jsonify({"error": f"Failed to retrieve catalog: {str(e)}"}), 500

        # Documentation endpoint
        if self.documentation_renderer:
            @self.catalog_bp.route(f"{path}/docs", methods=['GET'])
            def get_catalog_docs():
                """Get catalog documentation page."""
                try:
                    contracts = self.catalog_provider.get_catalog_contracts()
                    visible_contracts = self.catalog_provider.filter_visible_contracts(contracts)

                    contract_summaries = [self._contract_to_summary(c) for c in visible_contracts]
                    html_content = self.documentation_renderer.render_catalog_page(contract_summaries)

                    return Response(html_content, mimetype='text/html')

                except Exception as e:
                    return jsonify({"error": f"Failed to render catalog docs: {str(e)}"}), 500

        # Register blueprint
        self.app.register_blueprint(self.catalog_bp)

    def register_contract_endpoint(self, path: str = "/contracts/<category>/<api_major>", handler: Callable[..., Any] | None = None) -> None:
        """Register Flask routes for individual contracts."""

        @self.contracts_bp.route(f"{path}/openapi.json", methods=['GET'])
        def get_contract_spec(category: str, api_major: str):
            """Get OpenAPI specification for a specific contract."""
            try:
                if not self.contract_provider.is_contract_available(category, api_major):
                    return jsonify({"error": f"Contract not found: {category}:{api_major}"}), 404

                spec = self.contract_provider.get_contract_spec(category, api_major)
                if not spec:
                    return jsonify({"error": f"Contract specification not available: {category}:{api_major}"}), 404

                return jsonify(spec)

            except Exception as e:
                return jsonify({"error": f"Failed to retrieve contract: {str(e)}"}), 500

        @self.contracts_bp.route(f"{path}/metadata", methods=['GET'])
        def get_contract_metadata(category: str, api_major: str):
            """Get metadata for a specific contract."""
            try:
                metadata = self.contract_provider.get_contract_metadata(category, api_major)
                if not metadata:
                    return jsonify({"error": f"Contract metadata not found: {category}:{api_major}"}), 404

                return jsonify(metadata)

            except Exception as e:
                return jsonify({"error": f"Failed to retrieve metadata: {str(e)}"}), 500

        # Documentation endpoint
        if self.documentation_renderer:
            @self.contracts_bp.route(f"{path}/docs", methods=['GET'])
            def get_contract_docs(category: str, api_major: str):
                """Get documentation page for a specific contract."""
                try:
                    if not self.contract_provider.is_contract_available(category, api_major):
                        return jsonify({"error": f"Contract not found: {category}:{api_major}"}), 404

                    from html import escape as html_escape
                    safe_category = html_escape(category)
                    safe_api_major = html_escape(api_major)
                    contract_url = f"/contracts/{safe_category}/{safe_api_major}/openapi.json"
                    title = f"{safe_category} {safe_api_major} API Documentation"

                    if self.documentation_renderer is None:
                        return jsonify({"error": "Documentation renderer not available"}), 500
                    html_content = self.documentation_renderer.render_contract_page(contract_url, title)
                    return Response(html_content, mimetype='text/html')

                except Exception as e:
                    return jsonify({"error": f"Failed to render contract docs: {str(e)}"}), 500

        # Register blueprint
        self.app.register_blueprint(self.contracts_bp)

    def serve_openapi_spec(self, spec: dict, path: str) -> None:
        """Serve an OpenAPI specification at a custom path."""

        @self.app.route(path, methods=['GET'])
        def serve_custom_spec():
            """Serve custom OpenAPI specification."""
            return jsonify(spec)

    def register_health_endpoints(self) -> None:
        """Register health check endpoints."""

        @self.health_bp.route("/health", methods=['GET'])
        def health_check():
            """Liveness probe."""
            try:
                health_status = self.health_provider.check_health()
                status_code = 200 if health_status.get("status") == "healthy" else 503
                return jsonify(health_status), status_code
            except Exception as e:
                return jsonify({"status": "unhealthy", "error": str(e)}), 503

        @self.health_bp.route("/ready", methods=['GET'])
        def readiness_check():
            """Readiness probe."""
            try:
                readiness_status = self.health_provider.check_readiness()
                status_code = 200 if readiness_status.get("status") == "ready" else 503
                return jsonify(readiness_status), status_code
            except Exception as e:
                return jsonify({"status": "not_ready", "error": str(e)}), 503

        @self.health_bp.route("/info", methods=['GET'])
        def service_info():
            """Service information endpoint."""
            try:
                return jsonify(self.health_provider.get_service_info())
            except Exception as e:
                return jsonify({"error": f"Failed to get service info: {str(e)}"}), 500

        # Register blueprint
        self.app.register_blueprint(self.health_bp)

    def get_exposed_contracts(self, filters: Optional[dict] = None) -> List[ExposedContractRecord]:
        """Retrieve exposed contracts with optional filtering."""
        return self.catalog_provider.get_catalog_contracts(filters)

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


class FlaskAppFactory:
    """Factory for creating Flask applications with dependency injection."""

    @staticmethod
    def create_catalog_app(
        catalog_provider: CatalogProvider,
        contract_provider: ContractProvider,
        health_provider: HealthProvider,
        documentation_renderer: Optional[DocumentationRenderer] = None,
        app_name: str = "catalog_app"
    ) -> Flask:
        """
        Create a Flask application configured for catalog serving.

        Args:
            catalog_provider: Provider for catalog data
            contract_provider: Provider for individual contracts
            health_provider: Provider for health checks
            documentation_renderer: Optional documentation renderer
            app_name: Flask application name

        Returns:
            Configured Flask application
        """
        app = Flask(app_name)

        # Create catalog server with dependency injection
        catalog_server = FlaskCatalogServer(
            app=app,
            catalog_provider=catalog_provider,
            contract_provider=contract_provider,
            health_provider=health_provider,
            documentation_renderer=documentation_renderer
        )

        # Register all endpoints
        catalog_server.register_health_endpoints()
        catalog_server.register_catalog_endpoint()
        catalog_server.register_contract_endpoint()

        return app
