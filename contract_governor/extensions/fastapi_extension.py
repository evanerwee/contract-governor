"""
Contract Governor FastAPI Extension.

This module provides the ContractGovernorFastAPIExtension class which mounts
contract-driven routes, validation middleware, and documentation endpoints
onto a FastAPI application.
"""

import importlib
import inspect
import logging
import re
from collections.abc import Callable
from typing import Any, Dict, List, cast

try:
    from fastapi import APIRouter, Request
    from fastapi.responses import JSONResponse
    from fastapi.routing import APIRoute
    from starlette.routing import Route as StarletteRoute
except ImportError:
    raise ImportError("FastAPI is required for this module. " "Install with: pip install contract-governor[server]")

from ..core.contract_governor import ContractGovernor
from ..core.models import StipulationConfig
from ..core.stipulation_processor import StipulationProcessor

logger = logging.getLogger(__name__)


def camel_to_snake(name: str) -> str:
    """Convert camelCase to snake_case.

    Examples:
        registerDataPlane -> register_data_plane
        getDataPlane -> get_data_plane
        listDataPlanes -> list_data_planes
    """
    # Insert underscore before uppercase letters and convert to lowercase
    s1 = re.sub("(.)([A-Z][a-z]+)", r"\1_\2", name)
    return re.sub("([a-z0-9])([A-Z])", r"\1_\2", s1).lower()


def sort_routes_for_fastapi(paths: dict) -> list:
    """
    Sort OpenAPI paths so static routes come before parameterized routes.

    FastAPI matches routes in registration order. If a parameterized route like
    /files/{id} is registered before a static route like /files/search, requests
    to /files/search will incorrectly match the parameterized route.

    This function ensures static routes are always registered first at each path level.

    Args:
        paths: Dictionary of OpenAPI paths (keys are path strings)

    Returns:
        List of path strings sorted for correct FastAPI registration order

    Example:
        Input order:  ['/files', '/files/{id}', '/files/search']
        Output order: ['/files', '/files/search', '/files/{id}']
    """

    def route_priority(path: str) -> tuple:
        """Return a sort key that ranks static path segments before parameterized ones."""
        segments = path.strip("/").split("/")
        # 0 for static segments, 1 for parameterized {xxx} segments
        # This ensures static routes sort before parameterized at each level
        priority = tuple(1 if "{" in seg else 0 for seg in segments)
        # Sort by: path depth, then static-before-param priority, then alphabetically
        return (len(segments), priority, path)

    return sorted(paths.keys(), key=route_priority)


def auto_discover_handlers_from_stipulation(
    stipulation: Dict[str, Any], category: str, logger: logging.Logger | None = None
) -> List[tuple]:
    """
    Auto-discover handlers from a stipulation by introspecting the API class.

    This eliminates the need for services to manually register handlers.
    Contract-governor will automatically find all async methods on the API
    class and register them as handlers.

    Args:
        stipulation: Stipulation dict with implementation_module and implementation_router_class
        category: Category name for logging
        logger: Optional logger instance

    Returns:
        List of (method_name, handler_function) tuples

    Example stipulation::

        {
            "implementation_module": "ai4triage.data_plane.health.api",
            "implementation_router_class": "create_health_router",
            "stipulation_id": "health:v1"
        }
    """
    if logger is None:
        logger = logging.getLogger(__name__)

    handlers: list[tuple[str, Any]] = []

    impl_module = stipulation.get("implementation_module")
    impl_class = stipulation.get("implementation_router_class")

    if not impl_module or not impl_class:
        logger.warning(f"⚠️ Stipulation missing implementation_module or implementation_router_class for {category}")
        return handlers

    try:
        # Import the module
        logger.info(f"   Importing module: {impl_module}")
        module = importlib.import_module(impl_module)

        # Get the factory function/class
        if not hasattr(module, impl_class):
            logger.warning(f"⚠️ Module {impl_module} has no attribute '{impl_class}'")
            return handlers

        factory = getattr(module, impl_class)
        logger.info(f"   Found factory: {impl_class}")

        # Call the factory to get the API instance
        api_instance = factory()
        logger.info(f"   Created API instance: {type(api_instance).__name__}")

        # Discover all async methods on the API instance
        for attr_name in dir(api_instance):
            if attr_name.startswith("_"):  # Skip private methods
                continue

            try:
                attr = getattr(api_instance, attr_name)

                # Check if it's a callable async method
                if callable(attr) and inspect.iscoroutinefunction(attr):
                    handlers.append((attr_name, attr))

            except Exception as e:
                logger.debug(f"   ⚠️ Error checking attribute {attr_name}: {e}")
                continue

        logger.info(f"✅ Auto-discovered {len(handlers)} handlers for {category}")

    except ImportError as e:
        logger.warning(f"⚠️ Failed to import module {impl_module}: {e}")
    except Exception as e:
        logger.warning(f"⚠️ Failed to auto-discover handlers for {category}: {e}")
        import traceback

        logger.debug(traceback.format_exc())

    return handlers


class ContractGovernorFastAPIExtension:
    """
    Extends Contract Governor to generate FastAPI routes.

    PROPER ARCHITECTURE:
    1. OpenAPI contracts define the API surface (paths, methods, schemas)
    2. Implementation registry provides handlers by operationId
    3. This extension mounts OpenAPI paths and wires them to handlers
    4. NO DISCOVERY HACKS - clean registry lookup
    """

    def __init__(self, governor: ContractGovernor):
        """Initialize the FastAPI extension with a ContractGovernor and stipulation processor."""
        self.governor = governor
        self.stipulation_processor = StipulationProcessor(governor)
        self._contracts_with_implementations: set[str] = set()  # Track contracts with real implementations
        self._use_proper_architecture = governor.implementation_registry is not None

    def generate_fastapi_router(self) -> APIRouter:
        """
        Generate FastAPI router from exposed contracts.

        PROPER FLOW:
        1. Read OpenAPI contracts (source of truth for paths)
        2. For each path/method, get operationId
        3. Look up handler in implementation registry
        4. Mount the OpenAPI path with the handler
        5. NO DISCOVERY - clean registry lookup
        """
        router = APIRouter()

        # Track statistics for summary logging
        self._discovery_stats = {
            "real_implementations": 0,
            "mock_fallbacks": 0,
            "registry_lookup": 0,
            "catalog_guided": 0,
            "stipulation_guided": 0,
            "automatic_discovery": 0,
            "total_routes": 0,
        }
        self._mock_routes: list[str] = []  # Track which routes are using mocks

        # Use proper architecture if implementation registry is available
        if self._use_proper_architecture:
            logger.info("🎯 Using PROPER architecture: Implementation Registry")
            self._generate_router_via_registry(router)
        else:
            logger.warning("⚠️ Falling back to DEPRECATED discovery methods")
            self._generate_router_via_discovery(router)

        # Log summary of results
        self._log_discovery_summary()

        return router

    def _generate_router_via_registry(self, router: APIRouter) -> None:
        """
        Generate router using proper implementation registry (CORRECT WAY).

        This is the clean, SOLID approach:
        - OpenAPI contracts define paths (source of truth)
        - Implementation registry provides handlers by operationId
        - We mount paths and wire to handlers
        - No discovery hacks needed
        """
        # Log all contracts that will be mounted
        all_contracts = list(self.governor.list_exposed_contracts())
        logger.info(
            f"📋 Mounting {len(all_contracts)} contracts: {[f'{c.category}:{c.api_major_version}' for c in all_contracts]}"
        )
        logger.info("=" * 80)

        for exposed in all_contracts:
            spec = exposed.exposed_openapi_spec
            category = exposed.category
            version = exposed.api_major_version

            logger.info(f"📋 Processing contract: {category} {version}")

            # SOURCE OF TRUTH: OpenAPI paths
            # IMPORTANT: Sort paths so static routes come before parameterized routes
            # This prevents /files/search from matching /files/{id} with id="search"
            paths = spec.get("paths", {})
            sorted_paths = sort_routes_for_fastapi(paths)
            logger.debug(f"   Route order after sorting: {sorted_paths}")

            for path in sorted_paths:
                path_item = paths[path]
                for method in ["get", "post", "put", "delete", "patch"]:
                    if method in path_item:
                        operation = path_item[method]

                        # Skip forbidden methods
                        if self.stipulation_processor.should_forbid_method(category, version, method):
                            logger.debug(f"   ⛔ Skipping forbidden: {method.upper()} {path}")
                            continue

                        # Get operationId from OpenAPI spec
                        operation_id = operation.get("operationId")

                        if not operation_id:
                            logger.warning(f"   ⚠️ No operationId for {method.upper()} {path} - using mock")
                            self._add_mock_route(router, path, method, operation, category, version)
                            self._discovery_stats["mock_fallbacks"] += 1
                            self._discovery_stats["total_routes"] += 1
                            self._mock_routes.append(f"{method.upper()} {path} (no operationId)")
                            continue

                        # Look up handler in implementation registry
                        logger.debug(f"   🔍 Looking up operationId '{operation_id}' in Implementation Registry...")
                        handler = None
                        if self.governor.implementation_registry is not None:
                            handler = self.governor.implementation_registry.get_handler(operation_id)

                        # If not in registry, fall back to stipulation-based discovery
                        if not handler:
                            logger.warning(f"   ❌ Registry lookup failed for operationId '{operation_id}'")
                            logger.info(
                                f"   📋 Falling back to stipulation-based discovery for category '{category}'..."
                            )
                            stipulation = self._get_stipulation_for_category(category)
                            if stipulation and isinstance(stipulation, dict):
                                impl_module = stipulation.get("implementation_module", category)
                                router_class = stipulation.get("implementation_router_class")
                                stip_version = stipulation.get("stipulation_version", "unknown")
                                stip_id = stipulation.get("stipulation_id", "unknown")
                                last_updated = stipulation.get("last_updated", "unknown")
                                logger.info(
                                    f"   📄 Stipulation: id={stip_id}, v={stip_version}, updated={last_updated}"
                                )
                                logger.info(f"   📦 Implementation: module={impl_module}, class={router_class}")
                                router_obj = self._discover_via_stipulation(impl_module, stipulation)
                                if router_obj:
                                    versioned_path = self._insert_version_into_path(path, category, version)
                                    handler = self._find_matching_route(
                                        router_obj, versioned_path, method, operation_id
                                    )
                                    if handler:
                                        logger.info(f"   ✅ Found via stipulation: {method.upper()} {versioned_path}")
                                        self._discovery_stats["stipulation_guided"] += 1
                                    else:
                                        logger.warning(
                                            f"   ❌ Stipulation router found but no matching route for {method.upper()} {versioned_path}"
                                        )
                                else:
                                    logger.warning("   ❌ Failed to instantiate router from stipulation")
                            else:
                                logger.warning(f"   ❌ No stipulation found for category '{category}'")

                        if handler:
                            # Mount with real implementation
                            versioned_path = self._insert_version_into_path(path, category, version)
                            self._mount_real_route(router, versioned_path, method, handler, operation)
                            self._discovery_stats["real_implementations"] += 1
                            # Only count as registry_lookup if it came from registry, not stipulation
                            if (
                                self.governor.implementation_registry is not None
                                and self.governor.implementation_registry.get_handler(operation_id)
                            ):
                                self._discovery_stats["registry_lookup"] += 1
                            self._discovery_stats["total_routes"] += 1
                            if category:
                                self._contracts_with_implementations.add(category)
                                logger.debug(
                                    f"   📊 Added '{category}' to implementations set (now {len(self._contracts_with_implementations)} unique)"
                                )
                            logger.info(f"   ✅ {method.upper()} {versioned_path} → {operation_id}")
                        else:
                            # No handler found - use mock
                            versioned_path = self._insert_version_into_path(path, category, version)
                            self._add_mock_route(router, versioned_path, method, operation, category, version)
                            self._discovery_stats["mock_fallbacks"] += 1
                            self._discovery_stats["total_routes"] += 1
                            self._mock_routes.append(
                                f"{method.upper()} {versioned_path} (no handler for {operation_id})"
                            )
                            logger.warning(
                                f"   ⚠️ {method.upper()} {versioned_path} → Mock (no handler for {operation_id})"
                            )

    def _generate_router_via_discovery(self, router: APIRouter) -> None:
        """
        Generate router using deprecated discovery methods (BACKWARD COMPATIBILITY).

        This is the old, hacky approach that should be phased out.
        """
        for exposed in self.governor.list_exposed_contracts():
            spec = exposed.exposed_openapi_spec
            category = exposed.category
            version = exposed.api_major_version

            # Generate routes from OpenAPI paths
            # IMPORTANT: Sort paths so static routes come before parameterized routes
            # This prevents /files/search from matching /files/{id} with id="search"
            paths = spec.get("paths", {})
            sorted_paths = sort_routes_for_fastapi(paths)

            for path in sorted_paths:
                path_item = paths[path]
                for method in ["get", "post", "put", "delete", "patch"]:
                    if method in path_item:
                        # Skip forbidden methods
                        if self.stipulation_processor.should_forbid_method(category, version, method):
                            continue
                        # Insert version into path: /category/path -> /category/v1/path
                        versioned_path = self._insert_version_into_path(path, category, version)
                        self._add_route(router, versioned_path, method, path_item[method], category, original_path=path)

    def _mount_real_route(
        self, router: APIRouter, path: str, method: str, handler: Callable[..., Any], operation: dict
    ) -> None:
        """
        Mount a route with a real implementation handler.

        Args:
            router: FastAPI router to mount on
            path: API path from OpenAPI spec
            method: HTTP method
            handler: Handler function from implementation registry
            operation: OpenAPI operation object
        """
        # Mount the handler on the path
        getattr(router, method)(path)(handler)

    def _add_mock_route(
        self, router: APIRouter, path: str, method: str, operation: dict, category: str, version: str
    ) -> None:
        """
        Mount a route with a mock fallback handler.

        Args:
            router: FastAPI router to mount on
            path: API path from OpenAPI spec
            method: HTTP method
            operation: OpenAPI operation object
            category: API category
            version: API version
        """

        async def mock_handler(request: Request):
            """Return a mock JSON response derived from the OpenAPI operation examples."""
            responses = operation.get("responses", {})
            success = responses.get("200") or responses.get("201") or {}
            example = success.get("content", {}).get("application/json", {}).get("example")

            if example:
                return JSONResponse(content=example)

            return JSONResponse(
                content={
                    "message": f"Mock response for {path}",
                    "method": method.upper(),
                    "category": category,
                    "version": version,
                    "note": "This is a mock response - no handler registered",
                }
            )

        getattr(router, method)(path)(mock_handler)

    def _add_route(
        self,
        router: APIRouter,
        path: str,
        method: str,
        operation: dict,
        category: str | None = None,
        original_path: str | None = None,
    ):
        """Add single route to FastAPI router with full stipulation support."""
        self._discovery_stats["total_routes"] += 1

        # Use original contract path for discovery (before transformation)
        # This ensures we match against the router's actual path structure
        discovery_path = original_path if original_path else path

        # Try to discover real implementation first
        discovery_result = self._discover_implementation_with_metadata(discovery_path, method, category)

        if discovery_result["handler"]:
            # Use real implementation
            getattr(router, method)(path)(discovery_result["handler"])
            self._discovery_stats["real_implementations"] += 1

            # Track that this contract has at least one real implementation
            if category:
                self._contracts_with_implementations.add(category)
                logger.debug(
                    f"   📊 Added '{category}' to implementations set (now {len(self._contracts_with_implementations)} unique)"
                )

            # Track discovery method
            if discovery_result["method"] == "catalog":
                self._discovery_stats["catalog_guided"] += 1
                logger.info(
                    f"✅ {method.upper()} {path} → Real implementation (catalog-guided: {discovery_result['source']})"
                )
            elif discovery_result["method"] == "stipulation":
                self._discovery_stats["stipulation_guided"] += 1
                logger.info(
                    f"✅ {method.upper()} {path} → Real implementation (stipulation-guided: {discovery_result['source']})"
                )
            else:
                self._discovery_stats["automatic_discovery"] += 1
                logger.info(
                    f"✅ {method.upper()} {path} → Real implementation (auto-discovered: {discovery_result['source']})"
                )
        else:
            # Fall back to mock response from OpenAPI spec
            self._discovery_stats["mock_fallbacks"] += 1
            self._mock_routes.append(f"{method.upper()} {path} ({discovery_result['reason']})")

            async def handler(request: Request):
                """Return a mock JSON response when no real implementation is found."""
                responses = operation.get("responses", {})
                success = responses.get("200") or responses.get("201") or {}
                example = success.get("content", {}).get("application/json", {}).get("example")

                if example:
                    return JSONResponse(content=example)

                return JSONResponse(
                    content={
                        "message": f"Success from {path}",
                        "method": method.upper(),
                        "governed": True,
                        "stipulation_applied": True,
                    }
                )

            getattr(router, method)(path)(handler)
            logger.warning(f"⚠️ {method.upper()} {path} → Mock fallback (reason: {discovery_result['reason']})")

    def _extract_category_from_path(self, path: str) -> str:
        """
        Extract category from contract path.

        Args:
            path: Contract path (e.g., /dataplane-registration/v1/registration/dataplane)

        Returns:
            Category name (e.g., dataplane-registration)
        """
        path_parts = path.strip("/").split("/")
        if len(path_parts) >= 1:
            return path_parts[0]
        return ""

    def _get_stipulation_for_category(self, category: str) -> dict[str, Any] | StipulationConfig | None:
        """
        Load stipulation by category.

        Args:
            category: Category name

        Returns:
            Stipulation dictionary or None if not found
        """
        # Try v1 first (most common)
        stipulation_id = f"{category}:v1"
        stipulation = self.governor.stipulations.get(stipulation_id)

        if stipulation:
            # Convert StipulationConfig to dict if needed
            if hasattr(stipulation, "__dict__"):
                return {
                    "implementation_module": getattr(stipulation, "implementation_module", None),
                    "implementation_router_class": getattr(stipulation, "implementation_router_class", None),
                    "stipulation_id": getattr(stipulation, "stipulation_id", stipulation_id),
                }
            return stipulation

        return None

    def _insert_version_into_path(self, path: str, category: str, version: str) -> str:
        """
        Insert version into path after category prefix.

        Example:
            path: /registration/versions/{api_version}/instances
            category: component
            version: v1
            result: /component/v1/registration/versions/{api_version}/instances
        """
        # If path already starts with category, insert version after it
        if path.startswith(f"/{category}/"):
            return f"/{category}/{version}" + path[len(f"/{category}") :]
        # Otherwise prepend category/version
        return f"/{category}/{version}{path}"

    def _normalize_paths_for_matching(self, contract_path: str, router_path: str) -> bool:
        """
        Normalize paths to handle prefix differences.

        Contract paths include category/version prefix, implementation routers use category prefix only.
        Example:
            - Contract path: /prompts/v1/upload
            - Router path: /prompts/upload

        Args:
            contract_path: Full contract path with category/version prefix
            router_path: Router path with category prefix only

        Returns:
            True if paths match after normalization
        """
        # Strip version from contract path: /prompts/v1/upload -> /prompts/upload
        parts = contract_path.strip("/").split("/")
        if len(parts) >= 2 and parts[1].startswith("v"):
            # Remove version part: ['prompts', 'v1', 'upload'] -> ['prompts', 'upload']
            normalized_contract = "/" + "/".join([parts[0]] + parts[2:])
        else:
            normalized_contract = contract_path

        # Normalize both paths for comparison
        normalized_contract = normalized_contract.rstrip("/")
        normalized_router = router_path.rstrip("/")

        return normalized_contract == normalized_router

    def _discover_implementation_with_metadata(self, path: str, method: str, category: str | None = None) -> dict:
        """
        Discover implementation and return metadata about the discovery process.

        PRIORITY ORDER:
        1. API Catalog (authoritative source from control-plane)
        2. Stipulation fields (fallback for backward compatibility)
        3. Automatic pattern discovery (last resort)

        Returns:
            Dictionary with:
                - handler: The handler function or None
                - method: 'catalog', 'stipulation', 'automatic', or 'none'
                - source: Description of where the handler was found
                - reason: Reason for failure if handler is None
        """
        # Use provided category or extract from path
        if not category:
            category = self._extract_category_from_path(path)
        if not category:
            return {"handler": None, "method": "none", "source": None, "reason": "Could not extract category from path"}

        # PRIORITY 1: Check API Catalog first (authoritative source)
        logger.info(f"🔍 [{category}] Checking catalog for {method.upper()} {path}")
        catalog_impl = self.governor.get_implementation_from_catalog(category)
        if catalog_impl:
            logger.info(f"   ✅ Catalog found: {catalog_impl['module_path']}.{catalog_impl['class_name']}")
            router_obj = self._discover_via_catalog(catalog_impl)
            if router_obj:
                logger.info("   🔧 Router instantiated successfully")
                handler = self._find_matching_route(router_obj, path, method, operation_id=None)
                if handler:
                    logger.info(f"   🎉 CATALOG SUCCESS: {method.upper()} {path} → {catalog_impl['class_name']}")
                    return {
                        "handler": handler,
                        "method": "catalog",
                        "source": f"API Catalog: {catalog_impl['class_name']}",
                        "reason": None,
                    }
                else:
                    logger.warning(f"   ⚠️ Router found but no matching route for {method.upper()} {path}")
            else:
                logger.warning(f"   ⚠️ Failed to instantiate router from {catalog_impl['class_name']}")
        else:
            logger.warning(f"   ❌ Catalog lookup failed for category: {category}")

        # PRIORITY 2: Fall back to stipulation fields
        stipulation = self._get_stipulation_for_category(category)

        # Determine implementation module
        impl_module = category
        if stipulation and isinstance(stipulation, dict) and stipulation.get("implementation_module"):
            impl_module = stipulation["implementation_module"]

        # Try stipulation-guided discovery
        if stipulation and isinstance(stipulation, dict) and stipulation.get("implementation_router_class"):
            router_obj = self._discover_via_stipulation(impl_module, stipulation)
            if router_obj:
                handler = self._find_matching_route(router_obj, path, method, operation_id=None)
                if handler:
                    return {
                        "handler": handler,
                        "method": "stipulation",
                        "source": stipulation["implementation_router_class"],
                        "reason": None,
                    }
                else:
                    logger.debug(f"Stipulation found router but no matching route for {method.upper()} {path}")

        # PRIORITY 3: Try automatic discovery as last resort
        router_obj = self._discover_via_patterns(impl_module)
        if router_obj:
            handler = self._find_matching_route(router_obj, path, method, operation_id=None)
            if handler:
                return {"handler": handler, "method": "automatic", "source": f"{impl_module} module", "reason": None}

        # No implementation found
        logger.warning(f"   🚫 MOCK FALLBACK: No implementation found for {method.upper()} {path}")
        logger.warning(f"      Category: {category}")
        logger.warning("      Tried: catalog → stipulation → patterns")
        return {
            "handler": None,
            "method": "none",
            "source": None,
            "reason": f"No implementation found via catalog, stipulation, or patterns for {category}",
        }

    def _log_discovery_summary(self):
        """Log summary of discovery results."""
        stats = self._discovery_stats

        logger.info("=" * 80)
        if self._use_proper_architecture:
            logger.info("📊 Contract-Governor Mounting Summary (PROPER ARCHITECTURE)")
        else:
            logger.info("📊 Contract-Governor Discovery Summary (DEPRECATED)")
        logger.info("=" * 80)
        logger.info(f"Total routes processed: {stats['total_routes']}")
        logger.info(
            f"✅ Real implementations: {stats['real_implementations']} ({stats['real_implementations']/max(stats['total_routes'], 1)*100:.1f}%)"
        )

        if self._use_proper_architecture:
            logger.info(f"   📋 Registry lookup: {stats['registry_lookup']}")
            logger.info(f"   🎯 Stipulation fallback: {stats.get('stipulation_guided', 0)}")
        else:
            logger.info(f"   📚 Catalog-guided: {stats.get('catalog_guided', 0)}")
            logger.info(f"   🎯 Stipulation-guided: {stats['stipulation_guided']}")
            logger.info(f"   🔍 Auto-discovered: {stats['automatic_discovery']}")

        logger.info(
            f"⚠️ Mock fallbacks: {stats['mock_fallbacks']} ({stats['mock_fallbacks']/max(stats['total_routes'], 1)*100:.1f}%)"
        )
        if self._mock_routes:
            logger.warning("   Mock routes:")
            for mock_route in self._mock_routes:
                logger.warning(f"      • {mock_route}")
        logger.info(f"📋 Unique contract categories with implementations: {len(self._contracts_with_implementations)}")
        logger.info(f"   Categories: {', '.join(sorted(self._contracts_with_implementations))}")
        logger.info("=" * 80)

        # Success message
        if stats["mock_fallbacks"] == 0:
            logger.info("🎉 SUCCESS: 100% real implementations!")
        elif self._use_proper_architecture and stats["registry_lookup"] > 0 and stats.get("stipulation_guided", 0) > 0:
            logger.info(
                f"🎉 HYBRID SUCCESS: {stats['registry_lookup']} via Registry + {stats.get('stipulation_guided', 0)} via Stipulation"
            )

        # Diagnostic warnings
        if stats["mock_fallbacks"] > stats["real_implementations"]:
            logger.warning("🚨 HIGH MOCK FALLBACK RATE DETECTED!")
            if self._use_proper_architecture:
                logger.warning("   Register missing handlers in Implementation Registry")
                logger.warning("   Ensure OpenAPI specs have operationId for all operations")
            else:
                logger.warning("   Consider migrating to Implementation Registry pattern")
                logger.warning("   Check logs above for specific missing implementations")

    def has_real_implementation(self, category: str) -> bool:
        """Check if a contract category has any real implementations."""
        return category in self._contracts_with_implementations

    def _discover_via_catalog(self, catalog_impl: Dict[str, str]) -> APIRouter | None:
        """
        Discover router using API catalog (AUTHORITATIVE SOURCE).

        Args:
            catalog_impl: Dictionary with module_path and class_name from catalog

        Returns:
            APIRouter instance if found, None otherwise
        """
        module_path = catalog_impl["module_path"]
        class_name = catalog_impl["class_name"]

        try:
            module = __import__(module_path, fromlist=[""])

            if hasattr(module, class_name):
                router_class = getattr(module, class_name)

                # Handle both class-based and function-based routers
                if callable(router_class):
                    factory = self.governor.factory if hasattr(self.governor, "factory") else None

                    # Try with factory parameter first
                    try:
                        result = router_class(factory)

                        # Check if result is already an APIRouter
                        if isinstance(result, APIRouter):
                            logger.info(f"📚 Catalog discovery: {class_name}(factory) returned APIRouter")
                            return result
                        # Check if result has get_router() method
                        elif hasattr(result, "get_router"):
                            # Safe cast: get_router() convention always returns APIRouter
                            router_obj = cast(APIRouter, result.get_router())
                            logger.info(f"📚 Catalog discovery: {class_name}(factory).get_router()")
                            return router_obj
                        # Check if result has router attribute
                        elif hasattr(result, "router"):
                            # Safe cast: .router attribute convention always holds APIRouter
                            router_obj = cast(APIRouter, result.router)
                            logger.info(f"📚 Catalog discovery: {class_name}(factory).router")
                            return router_obj
                    except TypeError:
                        # Fall back to no-arg call
                        try:
                            result = router_class()

                            # Check if result is already an APIRouter
                            if isinstance(result, APIRouter):
                                logger.info(f"📚 Catalog discovery: {class_name}() returned APIRouter")
                                return result
                            # Check if result has get_router() method
                            elif hasattr(result, "get_router"):
                                # Safe cast: get_router() convention always returns APIRouter
                                router_obj = cast(APIRouter, result.get_router())
                                logger.info(f"📚 Catalog discovery: {class_name}().get_router()")
                                return router_obj
                            # Check if result has router attribute
                            elif hasattr(result, "router"):
                                # Safe cast: .router attribute convention always holds APIRouter
                                router_obj = cast(APIRouter, result.router)
                                logger.info(f"📚 Catalog discovery: {class_name}().router")
                                return router_obj
                        except TypeError:
                            pass

        except ImportError as e:
            logger.warning(f"⚠️ Catalog specified {module_path} but could not import: {e}")
        except Exception as e:
            logger.warning(f"⚠️ Error loading {class_name} from catalog: {e}")

        return None

    def _discover_via_stipulation(self, impl_module: str, stipulation: dict[str, Any]) -> APIRouter | None:
        """
        Discover router using stipulation guidance.

        Args:
            impl_module: Implementation module name
            stipulation: Stipulation dictionary with implementation guidance

        Returns:
            APIRouter instance if found, None otherwise
        """
        router_class_name = stipulation.get("implementation_router_class")
        stip_impl_module = stipulation.get("implementation_module")

        if not router_class_name:
            logger.error("❌ Stipulation missing 'implementation_router_class' field")
            return None

        if not stip_impl_module:
            logger.error("❌ Stipulation missing 'implementation_module' field")
            return None

        # Try multiple module path strategies for compatibility
        module_paths_to_try = [
            stip_impl_module,  # Try AS-IS first (for full paths like ai4triage.data_plane.*)
            f"ai4triage.control_plane.{stip_impl_module}",  # Fallback to prefixed (for short paths like authentication.api.*)
        ]

        logger.info(f"   📦 Attempting to load: {router_class_name}")

        module = None
        module_path = None
        for path_attempt in module_paths_to_try:
            try:
                module = __import__(path_attempt, fromlist=[""])
                module_path = path_attempt
                break
            except ImportError as e:
                logger.debug(f"   ⚠️ Could not import {path_attempt}: {e}")
                continue

        if not module:
            logger.error(f"   ❌ Could not import module using any strategy: {module_paths_to_try}")
            return None

        try:
            logger.info(f"   ✅ Module loaded: {module_path}")

            # ENHANCED DEBUG LOGGING
            available_items = [x for x in dir(module) if not x.startswith("_")]

            if not hasattr(module, router_class_name):
                logger.error(f"   ❌ Class '{router_class_name}' not found in {module_path}")
                logger.error("   ❌ STIPULATION MISMATCH DETECTED!")
                logger.error(f"   📋 Stipulation says: implementation_router_class='{router_class_name}'")
                logger.error(f"   📋 Module contains: {available_items}")

                # Check for similar names
                similar = [x for x in available_items if "router" in x.lower() or "api" in x.lower()]
                if similar:
                    logger.error(f"   💡 HINT: Found similar names: {similar}")
                    logger.error("   💡 HINT: Update stipulation to use one of these names")

                return None

            router_class = getattr(module, router_class_name)
            logger.info(f"   ✅ Class found: {router_class_name}")

            # Try calling with factory parameter first
            factory = self.governor.factory if hasattr(self.governor, "factory") else None

            # Get category and version from stipulation
            stip_id = stipulation.get("stipulation_id", "")
            category = stip_id.split(":")[0] if ":" in stip_id else stip_id
            version = stip_id.split(":")[1] if ":" in stip_id else "v1"
            prefix = f"/{category}"

            try:
                # Try with factory, prefix, and version
                result = router_class(factory, prefix=prefix, version=version)

                if isinstance(result, APIRouter):
                    logger.info(f"   ✅ {router_class_name}(factory, prefix) → APIRouter")
                    return result
                elif hasattr(result, "get_router"):
                    # Safe cast: get_router() convention always returns APIRouter
                    router_obj = cast(APIRouter, result.get_router())
                    logger.info(f"   ✅ {router_class_name}(factory, prefix).get_router() → APIRouter")
                    return router_obj
                elif hasattr(result, "router"):
                    # Safe cast: .router attribute convention always holds APIRouter
                    router_obj = cast(APIRouter, result.router)
                    logger.info(f"   ✅ {router_class_name}(factory, prefix).router → APIRouter")
                    return router_obj
            except TypeError:
                # Try with just factory
                try:
                    result = router_class(factory)

                    if isinstance(result, APIRouter):
                        logger.info(f"   ✅ {router_class_name}(factory) → APIRouter")
                        return result
                    elif hasattr(result, "get_router"):
                        # Safe cast: get_router() convention always returns APIRouter
                        router_obj = cast(APIRouter, result.get_router())
                        logger.info(f"   ✅ {router_class_name}(factory).get_router() → APIRouter")
                        return router_obj
                    elif hasattr(result, "router"):
                        # Safe cast: .router attribute convention always holds APIRouter
                        router_obj = cast(APIRouter, result.router)
                        logger.info(f"   ✅ {router_class_name}(factory).router → APIRouter")
                        return router_obj
                except TypeError:
                    # Fall back to no-arg instantiation
                    result = router_class()

                    if isinstance(result, APIRouter):
                        logger.info(f"   ✅ {router_class_name}() → APIRouter")
                        return result
                    elif hasattr(result, "get_router"):
                        # Safe cast: get_router() convention always returns APIRouter
                        router_obj = cast(APIRouter, result.get_router())
                        logger.info(f"   ✅ {router_class_name}().get_router() → APIRouter")
                        return router_obj
                    elif hasattr(result, "router"):
                        # Safe cast: .router attribute convention always holds APIRouter
                        router_obj = cast(APIRouter, result.router)
                        logger.info(f"   ✅ {router_class_name}().router → APIRouter")
                        return router_obj
                    else:
                        logger.error(f"   ❌ {router_class_name}() returned {type(result).__name__} with no router")
                        return None
                except Exception as e:
                    logger.error(f"   ❌ {router_class_name}() failed: {e}")
                    return None
            except Exception as e:
                logger.error(f"   ❌ Failed to instantiate {router_class_name}: {e}")
                return None

        except ImportError as e:
            logger.error(f"   ❌ Could not import {module_path}: {e}")
            return None
        except Exception as e:
            logger.error(f"   ❌ Unexpected error loading {router_class_name}: {e}")
            import traceback

            logger.debug(traceback.format_exc())
            return None

        return None

    def _discover_via_patterns(self, impl_module: str) -> APIRouter | None:
        """
        Discover router using automatic fallback patterns.

        Tries multiple discovery patterns in order:
        1. Class pattern: {Module}API with get_router() method
        2. Function patterns: create_{module}_router() and get_{module}_router()
        3. Variable pattern: direct router export

        Args:
            impl_module: Implementation module name

        Returns:
            APIRouter instance if found, None otherwise
        """
        # Try to import the implementation module
        # Try both full paths and prefixed paths for backward compatibility
        module_paths = [
            # Try full paths first (for ai4triage.data_plane.* or ai4triage.control_plane.*)
            f"{impl_module}.api.endpoints",
            f"{impl_module}.api.registration_router",
            f"{impl_module}.api",
            # Fallback to prefixed paths (for short paths like authentication, authorization, etc.)
            f"ai4triage.control_plane.{impl_module}.api.endpoints",
            f"ai4triage.control_plane.{impl_module}.api.registration_router",
            f"ai4triage.control_plane.{impl_module}.api",
        ]

        for module_path in module_paths:
            try:
                module = __import__(module_path, fromlist=[""])

                # Pattern 1: {Module}API class with get_router() method
                api_class_name = f"{impl_module.title()}API"
                if hasattr(module, api_class_name):
                    try:
                        api_class = getattr(module, api_class_name)
                        api_instance = api_class()
                        if hasattr(api_instance, "get_router"):
                            # Safe cast: get_router() convention always returns APIRouter
                            router_obj = cast(APIRouter, api_instance.get_router())
                            logger.info(f"🔍 Pattern discovery: Found {api_class_name}.get_router() in {module_path}")
                            return router_obj
                    except Exception as e:
                        logger.debug(f"Error with class pattern {api_class_name}: {e}")

                # Pattern 2a: create_{module}_router() function
                create_func_name = f"create_{impl_module}_router"
                if hasattr(module, create_func_name):
                    try:
                        router_func = getattr(module, create_func_name)
                        # Safe cast: create_*_router() factory functions return APIRouter
                        router_obj = cast(APIRouter, router_func())
                        logger.info(f"🔍 Pattern discovery: Found {create_func_name}() in {module_path}")
                        return router_obj
                    except Exception as e:
                        logger.debug(f"Error with function pattern {create_func_name}: {e}")

                # Pattern 2b: get_{module}_router() function
                get_func_name = f"get_{impl_module}_router"
                if hasattr(module, get_func_name):
                    try:
                        router_func = getattr(module, get_func_name)
                        # Safe cast: get_*_router() factory functions return APIRouter
                        router_obj = cast(APIRouter, router_func())
                        logger.info(f"🔍 Pattern discovery: Found {get_func_name}() in {module_path}")
                        return router_obj
                    except Exception as e:
                        logger.debug(f"Error with function pattern {get_func_name}: {e}")

                # Pattern 3: Direct router variable export
                if hasattr(module, "router"):
                    try:
                        # Safe cast: module-level 'router' variable is always APIRouter by convention
                        router_obj = cast(APIRouter, getattr(module, "router"))
                        logger.info(f"🔍 Pattern discovery: Found router variable in {module_path}")
                        return router_obj
                    except Exception as e:
                        logger.debug(f"Error with variable pattern 'router': {e}")

            except ImportError as e:
                logger.debug(f"Could not import {module_path}: {e}")
                continue
            except Exception as e:
                logger.debug(f"Error during pattern discovery in {module_path}: {e}")
                continue

        logger.debug(f"⚠️ No router found using automatic patterns for module: {impl_module}")
        return None

    def _find_matching_route(
        self, router: "APIRouter", contract_path: str, method: str, operation_id: str | None = None
    ) -> Callable[..., Any] | None:
        """
        Find matching route in discovered router.

        Uses path normalization to handle prefix differences and matches both
        path and HTTP method to return the actual handler function.

        If operation_id is provided, also tries to match by converting camelCase
        operationId to snake_case function name (Python convention).

        Args:
            router: APIRouter instance to search
            contract_path: Full contract path with category/version prefix
            method: HTTP method (e.g., post, get)
            operation_id: Optional OpenAPI operationId (e.g., registerDataPlane)

        Returns:
            Handler function if found, None otherwise
        """
        try:
            # If operationId provided, try matching by function name first
            if operation_id:
                snake_case_name = camel_to_snake(operation_id)
                logger.info(f"   🔍 Looking for operationId '{operation_id}' -> snake_case '{snake_case_name}'")

                for route in router.routes:
                    if not isinstance(route, (APIRoute, StarletteRoute)):
                        continue
                    endpoint_name = (
                        route.endpoint.__name__ if hasattr(route.endpoint, "__name__") else str(route.endpoint)
                    )

                    # Match by function name and HTTP method
                    if route.methods and endpoint_name == snake_case_name and method.upper() in route.methods:
                        logger.info(
                            f"   ✅ Matched by operationId: {operation_id} -> {snake_case_name}() on {route.path}"
                        )
                        endpoint = route.endpoint
                        return cast("Callable[..., Any] | None", endpoint)

            # Fall back to path matching
            for route in router.routes:
                if not isinstance(route, (APIRoute, StarletteRoute)):
                    continue
                route_path = route.path
                path_match = self._normalize_paths_for_matching(contract_path, route_path)

                logger.debug(
                    f"   Comparing: contract={contract_path} vs router={route_path}, match={path_match}, methods={list(route.methods or set())}"
                )

                # Use path normalization helper to handle prefix differences
                if path_match:
                    # Match HTTP method
                    if route.methods and method.upper() in route.methods:
                        logger.info(f"✅ Matched by path: {method.upper()} {contract_path} -> {route_path}")
                        endpoint = route.endpoint
                        return cast("Callable[..., Any] | None", endpoint)
                    else:
                        logger.debug(
                            f"   Path matched but method mismatch: need {method.upper()}, have {list(route.methods or set())}"
                        )

            # Log all available routes if no match
            available = [
                (
                    r.path,
                    list(r.methods or set()),
                    r.endpoint.__name__ if hasattr(r.endpoint, "__name__") else "unknown",
                )
                for r in router.routes
                if isinstance(r, (APIRoute, StarletteRoute))
            ]
            logger.warning(f"   ❌ No match for {method.upper()} {contract_path}")
            if operation_id:
                logger.warning(
                    f"      Searched for: operationId='{operation_id}' -> function='{camel_to_snake(operation_id)}'"
                )
            logger.warning(f"      Available routes: {available}")

        except Exception as e:
            logger.error(f"Error matching routes: {e}")

        return None
