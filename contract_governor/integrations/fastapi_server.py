"""
FastAPI catalog server implementation following SOLID principles.

This module contains only FastAPI-specific presentation and composition code:

- FastAPICatalogServer: HTTP presenter that delegates to domain providers
- FastAPIAppFactory: Factory for building a FastAPI app wired with providers
- ContractGovernorBootstrapper: Composition root for contract-driven routing
- mount_contract_governor: Backwards-compatible helper using the bootstrapper
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, cast

try:
    from fastapi import FastAPI, HTTPException, Query, Request
    from fastapi.responses import HTMLResponse, JSONResponse
except ImportError:
    raise ImportError("FastAPI is required for this module. " "Install with: pip install contract-governor[server]")

from ..core.contract_governor import ContractGovernor
from ..core.errors import (
    ContractNotFoundError,
    StipulationError,
    create_error_context,
)
from ..core.models import ExposedContractRecord
from ..core.monitoring import get_global_audit_logger
from ..interfaces.catalog_server import CatalogServer
from ..interfaces.documentation_renderer import DocumentationRenderer
from ..interfaces.serving_concerns import (
    CatalogProvider,
    ContractProvider,
    HealthProvider,
)
from .fastapi_error_handlers import register_error_handlers
from .monitoring_endpoints import register_monitoring_endpoints

# =============================================================================
# FASTAPI CATALOG SERVER (PRESENTER)
# =============================================================================


class FastAPICatalogServer(CatalogServer):
    """
    FastAPI implementation of CatalogServer following the Single Responsibility Principle.

    Responsibilities:
    - Define HTTP routes
    - Map HTTP requests to domain providers
    - Shape HTTP responses
    - Perform HTTP-level error mapping

    It does NOT:
    - Implement business rules
    - Load contracts from S3
    - Apply stipulations
    """

    def __init__(
        self,
        app: FastAPI,
        catalog_provider: CatalogProvider,
        contract_provider: ContractProvider,
        health_provider: HealthProvider,
        documentation_renderer: Optional[DocumentationRenderer] = None,
    ) -> None:
        """Initialize catalog server with FastAPI app and injected provider dependencies."""
        self.app = app
        self.catalog_provider = catalog_provider
        self.contract_provider = contract_provider
        self.health_provider = health_provider
        self.documentation_renderer = documentation_renderer

    # --------------------------------------------------------------------- #
    # Public registration API                                              #
    # --------------------------------------------------------------------- #

    def register_all_endpoints(self, catalog_path: str = "/api-catalog") -> None:
        """Register all standard endpoints for the catalog server."""
        self.register_health_endpoints()
        self.register_catalog_endpoint(path=catalog_path)
        self.register_contract_endpoint()

    def register_catalog_endpoint(
        self,
        path: str = "/api-catalog",
        handler: Optional[Callable[..., Any]] = None,
    ) -> None:
        """
        Register FastAPI endpoint for API catalog.

        If a custom handler is provided, it is mounted as-is.
        Otherwise, the default presenter handler is used.
        """
        if handler is not None:
            self.app.get(path, response_class=JSONResponse)(handler)
            return

        @self.app.get(path, response_class=JSONResponse)
        async def get_api_catalog(
            request: Request,
            api_major: Optional[str] = Query(None, description="Filter by API major version"),
            category: Optional[str] = Query(None, description="Filter by contract category"),
            visible_only: bool = Query(True, description="Show only visible contracts"),
        ) -> Dict[str, Any]:
            """Get API catalog with optional filtering."""
            audit_logger = get_global_audit_logger()

            try:
                filters: Dict[str, Any] = {}
                if api_major:
                    filters["api_major_version"] = api_major
                if category:
                    filters["category"] = category

                # Delegate to catalog provider
                contracts = self.catalog_provider.get_catalog_contracts(filters)

                if visible_only:
                    contracts = self.catalog_provider.filter_visible_contracts(contracts)

                contract_summaries = [self._contract_to_summary(c) for c in contracts]

                response: Dict[str, Any] = {
                    "contracts": contract_summaries,
                    "total": len(contracts),
                    "filters": {
                        "api_major": api_major,
                        "category": category,
                        "visible_only": visible_only,
                    },
                    "generated_at": datetime.now(timezone.utc).isoformat(),
                }

                if audit_logger is not None:
                    audit_logger.log_catalog_access(
                        operation="get_catalog",
                        success=True,
                        contract_count=len(contracts),
                        client_ip=self._get_client_ip(request),
                        user_agent=request.headers.get("user-agent"),
                        filters={
                            "api_major": api_major,
                            "category": category,
                            "visible_only": visible_only,
                        },
                    )
                return response

            except StipulationError:
                # Let global error handlers & loggers do their job
                if audit_logger is not None:
                    audit_logger.log_catalog_access(
                        operation="get_catalog",
                        success=False,
                        contract_count=0,
                        client_ip=self._get_client_ip(request),
                        user_agent=request.headers.get("user-agent"),
                        filters={
                            "api_major": api_major,
                            "category": category,
                            "visible_only": visible_only,
                        },
                    )
                raise
            except Exception as exc:
                if audit_logger is not None:
                    audit_logger.log_catalog_access(
                        operation="get_catalog",
                        success=False,
                        contract_count=0,
                        client_ip=self._get_client_ip(request),
                        user_agent=request.headers.get("user-agent"),
                        filters={
                            "api_major": api_major,
                            "category": category,
                            "visible_only": visible_only,
                        },
                    )
                context = create_error_context(
                    service_name="fastapi_catalog_server",
                    operation="get_catalog",
                )
                raise StipulationError(
                    message=f"Failed to retrieve catalog: {exc}",
                    error_code="CATALOG_RETRIEVAL_FAILED",
                    context=context,
                    cause=exc,
                ) from exc

        if self.documentation_renderer:

            @self.app.get(f"{path}/docs", response_class=HTMLResponse)
            async def get_catalog_docs() -> HTMLResponse:
                """Render HTML documentation for the catalog."""
                try:
                    contracts = self.catalog_provider.get_catalog_contracts()
                    visible_contracts = self.catalog_provider.filter_visible_contracts(contracts)
                    summaries = [self._contract_to_summary(c) for c in visible_contracts]
                    renderer = self.documentation_renderer
                    if renderer is None:
                        raise HTTPException(
                            status_code=500,
                            detail="Documentation renderer not configured",
                        )
                    html = renderer.render_catalog_page(summaries)
                    return HTMLResponse(content=html)
                except Exception as exc:
                    # Presentation-only: simple 500 is fine here
                    raise HTTPException(
                        status_code=500,
                        detail=f"Failed to render catalog docs: {exc}",
                    ) from exc

    def register_contract_endpoint(
        self,
        path: str = "/contracts/{category}/{api_major}",
        handler: Optional[Callable[..., Any]] = None,
    ) -> None:
        """
        Register FastAPI endpoint(s) for individual contracts.

        - `<path>/openapi.json` : OpenAPI spec for a specific contract
        - `<path>/metadata`     : Metadata for a specific contract
        - `<path>/docs`         : HTML docs (if DocumentationRenderer is provided)
        """
        # ------------------------------------------------------------------ #
        # OpenAPI spec                                                       #
        # ------------------------------------------------------------------ #
        if handler is not None:
            self.app.get(f"{path}/openapi.json", response_class=JSONResponse)(handler)
        else:

            @self.app.get(f"{path}/openapi.json", response_class=JSONResponse)
            async def get_contract_spec(
                request: Request,
                category: str,
                api_major: str,
            ) -> Any:
                """Get OpenAPI specification for a specific contract."""
                audit_logger = get_global_audit_logger()

                try:
                    if not self.contract_provider.is_contract_available(category, api_major):
                        context = create_error_context(
                            service_name="fastapi_catalog_server",
                            contract_category=category,
                            api_major_version=api_major,
                            operation="get_contract_spec",
                        )
                        raise ContractNotFoundError(
                            category=category,
                            api_major_version=api_major,
                            contract_type="exposed",
                            context=context,
                        )

                    spec = self.contract_provider.get_contract_spec(category, api_major)
                    if not spec:
                        context = create_error_context(
                            service_name="fastapi_catalog_server",
                            contract_category=category,
                            api_major_version=api_major,
                            operation="get_contract_spec",
                        )
                        raise ContractNotFoundError(
                            category=category,
                            api_major_version=api_major,
                            contract_type="exposed",
                            context=context,
                        )

                    if audit_logger is not None:
                        audit_logger.log_contract_access(
                            contract_category=category,
                            api_major_version=api_major,
                            operation="get_contract_spec",
                            success=True,
                            client_ip=self._get_client_ip(request),
                            user_agent=request.headers.get("user-agent"),
                        )
                    return spec

                except (ContractNotFoundError, StipulationError):
                    if audit_logger is not None:
                        audit_logger.log_contract_access(
                            contract_category=category,
                            api_major_version=api_major,
                            operation="get_contract_spec",
                            success=False,
                            client_ip=self._get_client_ip(request),
                            user_agent=request.headers.get("user-agent"),
                        )
                    raise
                except HTTPException:
                    if audit_logger is not None:
                        audit_logger.log_contract_access(
                            contract_category=category,
                            api_major_version=api_major,
                            operation="get_contract_spec",
                            success=False,
                            client_ip=self._get_client_ip(request),
                            user_agent=request.headers.get("user-agent"),
                        )
                    raise
                except Exception as exc:
                    if audit_logger is not None:
                        audit_logger.log_contract_access(
                            contract_category=category,
                            api_major_version=api_major,
                            operation="get_contract_spec",
                            success=False,
                            client_ip=self._get_client_ip(request),
                            user_agent=request.headers.get("user-agent"),
                        )
                    context = create_error_context(
                        service_name="fastapi_catalog_server",
                        contract_category=category,
                        api_major_version=api_major,
                        operation="get_contract_spec",
                    )
                    raise StipulationError(
                        message=f"Failed to retrieve contract: {exc}",
                        error_code="CONTRACT_RETRIEVAL_FAILED",
                        context=context,
                        cause=exc,
                    ) from exc

        # ------------------------------------------------------------------ #
        # Metadata                                                           #
        # ------------------------------------------------------------------ #

        @self.app.get(f"{path}/metadata", response_class=JSONResponse)
        async def get_contract_metadata(category: str, api_major: str) -> Any:
            """Get metadata for a specific contract."""
            try:
                metadata = self.contract_provider.get_contract_metadata(category, api_major)
                if not metadata:
                    raise HTTPException(
                        status_code=404,
                        detail=f"Contract metadata not found: {category}:{api_major}",
                    )
                return metadata
            except HTTPException:
                raise
            except Exception as exc:
                raise HTTPException(
                    status_code=500,
                    detail=f"Failed to retrieve metadata: {exc}",
                ) from exc

        # ------------------------------------------------------------------ #
        # HTML docs                                                          #
        # ------------------------------------------------------------------ #
        if self.documentation_renderer:

            @self.app.get(f"{path}/docs", response_class=HTMLResponse)
            async def get_contract_docs(
                category: str,
                api_major: str,
            ) -> HTMLResponse:
                """Get documentation page for a specific contract."""
                try:
                    if not self.contract_provider.is_contract_available(category, api_major):
                        raise HTTPException(
                            status_code=404,
                            detail=f"Contract not found: {category}:{api_major}",
                        )

                    from html import escape as html_escape

                    safe_category = html_escape(category)
                    safe_api_major = html_escape(api_major)
                    contract_url = f"/contracts/{safe_category}/{safe_api_major}/openapi.json"
                    title = f"{safe_category} {safe_api_major} API Documentation"
                    renderer = self.documentation_renderer
                    if renderer is None:
                        raise HTTPException(
                            status_code=500,
                            detail="Documentation renderer not configured",
                        )
                    html = renderer.render_contract_page(contract_url, title)
                    return HTMLResponse(content=html)
                except HTTPException:
                    raise
                except Exception as exc:
                    raise HTTPException(
                        status_code=500,
                        detail=f"Failed to render contract docs: {exc}",
                    ) from exc

    def serve_openapi_spec(self, spec: Dict[str, Any], path: str) -> None:
        """Serve a specific OpenAPI spec at a custom path."""

        @self.app.get(path, response_class=JSONResponse)
        async def serve_custom_spec() -> Dict[str, Any]:
            """Serve the pre-loaded OpenAPI spec as a JSON response."""
            return spec

    def register_health_endpoints(self) -> None:
        """Register health/readiness/info endpoints for Kubernetes probes."""

        @self.app.get("/health", response_class=JSONResponse)
        async def health_check() -> JSONResponse:
            """Return service health status for liveness probes."""
            try:
                status = self.health_provider.check_health()
                code = 200 if status.get("status") == "healthy" else 503
                return JSONResponse(content=status, status_code=code)
            except Exception as exc:
                return JSONResponse(
                    content={"status": "unhealthy", "error": str(exc)},
                    status_code=503,
                )

        @self.app.get("/ready", response_class=JSONResponse)
        async def readiness_check() -> JSONResponse:
            """Return service readiness status for readiness probes."""
            try:
                status = self.health_provider.check_readiness()
                code = 200 if status.get("status") == "ready" else 503
                return JSONResponse(content=status, status_code=code)
            except Exception as exc:
                return JSONResponse(
                    content={"status": "not_ready", "error": str(exc)},
                    status_code=503,
                )

        @self.app.get("/info", response_class=JSONResponse)
        async def service_info() -> Any:
            """Return service metadata and version information."""
            try:
                return self.health_provider.get_service_info()
            except Exception as exc:
                raise HTTPException(
                    status_code=500,
                    detail=f"Failed to get service info: {exc}",
                ) from exc

    # ------------------------------------------------------------------ #
    # Helper methods                                                     #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _get_client_ip(request: Request) -> Optional[str]:
        """Extract the client IP address from the request connection info.

        Args:
            request: The incoming HTTP request.

        Returns:
            Client IP address string, or None if not available.
        """
        client = getattr(request, "client", None)
        return getattr(client, "host", None) if client else None

    def get_exposed_contracts(self, filters: Optional[Dict[str, Any]] = None) -> List[ExposedContractRecord]:
        """Convenience wrapper used by non-HTTP tiers (e.g., testing)."""
        return self.catalog_provider.get_catalog_contracts(filters)

    def _contract_to_summary(self, contract: ExposedContractRecord) -> Dict[str, Any]:
        """Convert an ExposedContractRecord into a thin DTO for the API."""
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
            "exposed_at": (contract.exposed_at.isoformat() if contract.exposed_at else None),
            "stipulation_applied": contract.stipulation_applied,
        }


# =============================================================================
# FASTAPI APP FACTORY (COMPOSITION ROOT FOR PRESENTATION)
# =============================================================================


class FastAPIAppFactory:
    """
    Factory for creating FastAPI applications with proper dependency injection.

    This is the FastAPI-specific composition root used by the FrameworkAdapter layer.
    """

    @staticmethod
    def create_catalog_app(
        catalog_provider: CatalogProvider,
        contract_provider: ContractProvider,
        health_provider: HealthProvider,
        documentation_renderer: Optional[DocumentationRenderer] = None,
        title: str = "API Contract Catalog",
        description: str = "Centralized catalog of governed API contracts",
        version: str = "1.0.0",
    ) -> FastAPI:
        """
        Create a FastAPI application configured for catalog serving.

        This function wires:
        - FastAPI instance
        - Error handlers
        - Monitoring endpoints
        - FastAPICatalogServer routes
        """
        app = FastAPI(
            title=title,
            description=description,
            version=version,
            docs_url="/internal/docs",  # Internal FastAPI docs
            redoc_url="/internal/redoc",  # Internal ReDoc
        )

        # Cross-cutting concerns
        register_error_handlers(app, include_traceback=False, log_errors=True)
        register_monitoring_endpoints(app, prefix="/monitoring")

        # HTTP presenter
        catalog_server = FastAPICatalogServer(
            app=app,
            catalog_provider=catalog_provider,
            contract_provider=contract_provider,
            health_provider=health_provider,
            documentation_renderer=documentation_renderer,
        )

        catalog_server.register_all_endpoints()

        return app


# =============================================================================
# CONTRACT GOVERNOR BOOTSTRAP (DOMAIN COMPOSITION)
# =============================================================================


class ContractGovernorBootstrapper:
    """
    Bootstrapper that wires ContractGovernor and FastAPI using contract-driven routing.

    Responsibilities:
    - Load contracts + stipulations from a ContractSource
    - Populate a ContractRegistry
    - Initialize ContractGovernor
    - Use FastAPI extension to mount governed routes

    This is intentionally separate from FastAPICatalogServer to keep SRP:
    catalog server: read-only catalog/presentation.
    bootstrapper: contract ingestion + routing.
    """

    def __init__(
        self,
        contract_source: Any,
        contract_registry: Any,
        governor_cls: Any,
        fastapi_extension_cls: Any,
        logger: Any,
    ) -> None:
        """Initialize bootstrapper with contract source, registry, and extension classes."""
        self._contract_source = contract_source
        self._contract_registry = contract_registry
        self._governor_cls = governor_cls
        self._fastapi_extension_cls = fastapi_extension_cls
        self._logger = logger

    def bootstrap(
        self,
        app: FastAPI,
        implementation_registry: Any,
        mount_prefix: str = "/api",
        gateway_base_url: Optional[str] = None,
        api_catalog: Optional[Dict[str, Any]] = None,
    ) -> Any:
        """
        Perform full contract-driven bootstrap and mount routes on the given app.

        Returns:
            An initialized ContractGovernor instance.
        """
        logger = self._logger

        logger.info("=" * 80)
        logger.info("🎯 PURE CONTRACT-DRIVEN ARCHITECTURE")
        logger.info("   OpenAPI contracts from source = ONLY source of truth")
        logger.info("=" * 80)

        # 1) Load stipulations
        logger.info("📋 Step 1: Loading stipulations")
        stipulations = self._contract_source.load_stipulations()
        logger.info("   ✓ Loaded %d stipulations", len(stipulations))
        for stip_id in stipulations.keys():
            logger.info("      - %s", stip_id)

        # 2) Initialize ContractGovernor
        logger.info("📋 Step 2: Initializing Contract-Governor")
        governor = self._governor_cls(
            registry=self._contract_registry,
            stipulations=stipulations,
            implementation_registry=implementation_registry,
            api_catalog=api_catalog,
        )

        # Add /api-catalog endpoint for api.explorer compatibility
        @app.get("/api-catalog")
        async def get_api_catalog():
            """API catalog endpoint for api.explorer compatibility."""
            exposed_contracts = governor.list_exposed_contracts()

            # Filter to only show contracts with real implementations (like old code)
            contracts_list = []
            for contract in exposed_contracts:
                # Only include contracts that were successfully exposed
                if not contract.exposed_openapi_spec:
                    continue

                spec = contract.exposed_openapi_spec
                info = spec.get("info", {})
                title = info.get("title", f"{contract.category} API")
                description = info.get("description", f"{contract.category} endpoints")
                openapi_version = spec.get("openapi", "3.0.0")

                # Extract i18n translations if available
                title_i18n = info.get("x-title-i18n", {})
                description_i18n = info.get("x-description-i18n", {})

                # Extract stipulation version from the stipulation_applied field (e.g., "authentication:v1")
                stipulation_id = contract.stipulation_applied
                stipulation_version = None
                if stipulation_id and ":" in stipulation_id:
                    # Get the actual stipulation config to extract version
                    stip_config = governor.stipulations.get(stipulation_id)
                    if stip_config and hasattr(stip_config, "stipulation_version"):
                        stipulation_version = stip_config.stipulation_version

                contracts_list.append(
                    {
                        "category": contract.category,
                        "version": contract.api_major_version,  # e.g., "v1"
                        "contract_version": contract.contract_version,  # e.g., "1.0.0" from OpenAPI info.version
                        "openapi_version": openapi_version,  # e.g., "3.0.3"
                        "stipulation_version": stipulation_version,  # e.g., "1.0.0"
                        "title": title,  # CRITICAL: This is what api.explorer needs
                        "description": description,
                        "title_i18n": title_i18n,  # NEW: i18n translations
                        "description_i18n": description_i18n,  # NEW: i18n translations
                        "openapi_url": f"/contracts/{contract.category}/{contract.api_major_version}/openapi.json",
                        "docs_url": f"/contracts/{contract.category}/{contract.api_major_version}/docs",
                    }
                )

            return {
                "contracts": contracts_list,
                "total": len(contracts_list),
                "generated_at": datetime.now(timezone.utc).isoformat(),
            }

        # 3) Load contracts
        logger.info("📋 Step 3: Loading OpenAPI contracts")
        contracts = self._contract_source.load_contracts()
        logger.info("   ✓ Found %d contracts", len(contracts))

        if not contracts:
            logger.warning("   ⚠️ NO CONTRACTS FOUND IN CONTRACT SOURCE!")

        # 3.5) Get deployment role for filtering
        import os

        deployment_role = os.getenv("DEPLOYMENT_ROLE", "")
        if deployment_role:
            logger.info("📋 Step 3.5: Deployment role filtering active")
            logger.info("   DEPLOYMENT_ROLE=%s", deployment_role)

        # 4) Ingest + expose contracts
        logger.info("📋 Step 4: Ingesting and exposing contracts")
        skipped_contracts = []
        for contract_data in contracts:
            category = contract_data["category"]
            api_major = contract_data["api_major"]

            # Check deployment role filtering via stipulation
            stip_key = f"{category}:{api_major}"
            stip_config = stipulations.get(stip_key)

            if stip_config and deployment_role:
                if not stip_config.should_mount_for_role(deployment_role):
                    logger.info("   ⏭️ Skipping %s %s (not for role '%s')", category, api_major, deployment_role)
                    skipped_contracts.append(f"{category}:{api_major}")
                    continue

            governor.ingest_backend_contract(
                contract=contract_data["contract"],
                category=category,
                api_major=api_major,
                source_service=contract_data["source_service"],
                contract_file_path=contract_data["contract_file_path"],
                service_version=contract_data.get("service_version"),
            )

            # Use provided gateway_base_url or construct from mount_prefix
            contract_gateway_url = (
                f"{gateway_base_url}/{category}/{api_major}"
                if gateway_base_url
                else f"{mount_prefix}/{category}/{api_major}"
            )

            try:
                governor.expose_contract(
                    category=category,
                    api_major=api_major,
                    gateway_base_url=contract_gateway_url,
                )
                logger.info("   ✓ Exposed %s %s", category, api_major)
            except Exception as e:
                # Import error types for clean handling
                from ..core.errors import StipulationNotFoundError, StipulationParseError

                root_cause = e.__cause__ if e.__cause__ else e

                if isinstance(root_cause, StipulationNotFoundError):
                    # Clean one-liner — no traceback needed for a missing file
                    logger.warning(
                        "   ⚠️ Skipped %s %s — no stipulation file found. "
                        "Create stipulations/%s_%s.yaml or remove the contract from S3.",
                        category,
                        api_major,
                        category,
                        api_major,
                    )
                elif isinstance(root_cause, StipulationParseError):
                    logger.error(
                        "   ❌ Skipped %s %s — stipulation parse error: %s",
                        category,
                        api_major,
                        root_cause,
                    )
                else:
                    # Unexpected error — full traceback is useful here
                    logger.error("   ❌ Failed to expose %s %s: %s", category, api_major, str(e))
                    import traceback

                    logger.error("   Full traceback: %s", traceback.format_exc())

                skipped_contracts.append(f"{category}:{api_major}")
                continue

        if skipped_contracts:
            logger.info(
                "   📋 Skipped %d contracts for role '%s': %s",
                len(skipped_contracts),
                deployment_role,
                skipped_contracts,
            )

        # 5) Generate FastAPI router
        logger.info("📋 Step 5: Generating FastAPI router from OpenAPI contracts")
        extension = self._fastapi_extension_cls(governor)
        governed_router = extension.generate_fastapi_router()

        # LOG ALL ROUTES BEING REGISTERED
        logger.info("=" * 80)
        logger.info("🔍 ROUTE REGISTRATION EVIDENCE:")
        logger.info(f"   Total routes in router: {len(governed_router.routes)}")
        for i, route in enumerate(governed_router.routes, 1):
            if hasattr(route, "path") and hasattr(route, "methods"):
                methods = ",".join(route.methods) if route.methods else "N/A"
                logger.info(f"   {i}. {methods:6s} {mount_prefix}{route.path}")
        logger.info("=" * 80)

        # 6) Mount router on app
        logger.info("📋 Step 6: Mounting on FastAPI app at %s", mount_prefix)
        app.include_router(governed_router, prefix=mount_prefix)

        # LOG FINAL APP ROUTES
        logger.info("=" * 80)
        logger.info("🔍 FINAL APP ROUTES AFTER MOUNTING:")
        logger.info(f"   Total routes in app: {len(app.routes)}")
        for i, route in enumerate(app.routes, 1):
            if hasattr(route, "path") and hasattr(route, "methods"):
                methods = ",".join(route.methods) if route.methods else "N/A"
                logger.info(f"   {i}. {methods:6s} {route.path}")
        logger.info("=" * 80)

        logger.info("=" * 80)
        logger.info("✅ CONTRACT-DRIVEN ARCHITECTURE ACTIVE")
        logger.info("   Contracts loaded: %d", len(contracts))
        logger.info("   Stipulations applied: %d", len(stipulations))
        logger.info("   Mounted at: %s", mount_prefix)
        logger.info("   ALL paths defined by OpenAPI contracts")
        logger.info("   ZERO hardcoded paths")
        logger.info("=" * 80)

        # Initialize proper SOLID providers
        from .catalog_providers import (
            BasicHealthProvider,
            ContractGovernorCatalogProvider,
            ContractGovernorContractProvider,
        )

        ContractGovernorCatalogProvider(governor)
        ContractGovernorContractProvider(governor)
        BasicHealthProvider()

        # Serve contract specs directly (like the old working code)
        for exposed in governor.list_exposed_contracts():
            spec = exposed.exposed_openapi_spec.copy()

            # Create endpoint for this specific contract
            @app.get(f"/contracts/{exposed.category}/{exposed.api_major_version}/openapi.json")
            async def serve_contract_spec(spec=spec):
                """Serve the OpenAPI spec JSON for this specific contract."""
                return spec

        return governor


# =============================================================================
# BACKWARDS-COMPATIBLE ENTRYPOINT
# =============================================================================


def mount_contract_governor(
    app: FastAPI,
    implementation_registry: Any,
    s3_bucket: str,
    control_plane_version: str,
    mount_prefix: str = "/api",
    gateway_base_url: Optional[str] = None,
    s3_client: Optional[Any] = None,
    api_catalog: Optional[Dict[str, Any]] = None,
    server_url_strategy: Optional[str] = None,
    server_url_config: Optional[Dict[str, Any]] = None,
) -> "ContractGovernor":
    """
    Mount Contract-Governor on FastAPI app using S3 as the contract source.

    This is a thin convenience wrapper around ContractGovernorBootstrapper
    and is kept for API compatibility.

    Steps:
    1. Create S3ContractSource
    2. Create InMemoryContractRegistry
    3. Construct ContractGovernorBootstrapper
    4. Bootstrap and mount governed routes
    """
    import logging

    import boto3

    from ..core.contract_governor import ContractGovernor
    from ..core.registry import InMemoryContractRegistry
    from ..extensions.fastapi_extension import ContractGovernorFastAPIExtension
    from ..loaders.s3_loader import S3ContractSource

    logger = logging.getLogger(__name__)

    # Initialize S3 client if not provided
    if s3_client is None:
        s3_client = boto3.client("s3")

    contract_source = S3ContractSource(
        s3_client=s3_client,
        bucket_name=s3_bucket,
        control_plane_version=control_plane_version,
        contracts_prefix="contracts",
        stipulations_prefix="stipulations",
    )

    # Apply server URL strategy to stipulations if provided
    if server_url_strategy and server_url_config:
        logger.info(f"🔗 Applying server URL strategy: {server_url_strategy}")
        logger.info(f"🔗 Server URL config: {server_url_config}")

        # Load stipulations and apply URL strategy
        original_load_stipulations = contract_source.load_stipulations

        def load_stipulations_with_url_strategy():
            """Load stipulations and inject server URLs from the configured strategy."""
            stipulations = original_load_stipulations()

            # Build server_urls from config
            if server_url_strategy == "env_based" and server_url_config:
                import os

                env_var = server_url_config.get("env_var", "PUBLIC_API_URL")
                fallback = server_url_config.get("fallback", "")
                base_url = os.getenv(env_var, fallback)

                if base_url:
                    server_urls = [{"url": base_url, "description": "Public API"}]

                    for stip in stipulations.values():
                        # StipulationConfig is a dataclass, set attribute directly
                        if hasattr(stip, "server_urls"):
                            stip.server_urls = server_urls

                    logger.info(f"✅ Applied server URL {base_url} to {len(stipulations)} stipulations")

            return stipulations

        setattr(contract_source, "load_stipulations", load_stipulations_with_url_strategy)

    contract_registry = InMemoryContractRegistry()

    bootstrapper = ContractGovernorBootstrapper(
        contract_source=contract_source,
        contract_registry=contract_registry,
        governor_cls=ContractGovernor,
        fastapi_extension_cls=ContractGovernorFastAPIExtension,
        logger=logger,
    )

    # Safe: ContractGovernorBootstrapper.bootstrap always returns a ContractGovernor instance
    return cast(
        ContractGovernor,
        bootstrapper.bootstrap(
            app=app,
            implementation_registry=implementation_registry,
            mount_prefix=mount_prefix,
            gateway_base_url=gateway_base_url,
            api_catalog=api_catalog,
        ),
    )
