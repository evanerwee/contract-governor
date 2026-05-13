"""
Stipulation Processor for contract template expansion and variable substitution.

This module provides the StipulationProcessor class which handles stipulation-driven
transformations including multi-tenant template expansion and variable discovery.
"""

import logging
from typing import Any, Dict, List, Optional, cast

from .template_models import (
    ContractInstance,
    MultiTenantStipulation,
    TemplateExpander,
    VariableDiscovery,
)

logger = logging.getLogger(__name__)


class StipulationProcessor:
    """Processes stipulation transformations with variable substitution."""

    def __init__(self, governor):
        """Initialize processor with a ContractGovernor instance and supporting components."""
        self.governor = governor
        self.template_expander = TemplateExpander()
        self.variable_discovery = VariableDiscovery()
        self._multi_tenant_stipulations: Dict[str, MultiTenantStipulation] = {}

    def apply_path_transformation(self, category: str, version: str, path: str) -> str:
        """Apply stipulation path transformations including variables."""
        try:
            stipulation = self.governor.get_stipulation_for_contract(category, version)
            if not stipulation:
                logger.warning(f"No stipulation found for {category}:{version}")
                return f"/{category}/{version}{path}"

            # Debug logging
            logger.debug(
                f"Processing stipulation for {category}:{version}, proxy_prefix_format: {getattr(stipulation, 'proxy_prefix_format', 'NOT_FOUND')}"
            )

            # Apply proxy_prefix_format with variable substitution
            if hasattr(stipulation, "proxy_prefix_format") and stipulation.proxy_prefix_format is not None:
                prefix = stipulation.proxy_prefix_format.strip("/")

                # Variable substitution support
                variables = {
                    "category": category,
                    "version": version,
                    "api_major": version.split(".")[0] if "." in version else version,
                    "tenant_id": "{tenant_id}",  # Preserve for runtime
                    "user_id": "{user_id}",  # Preserve for runtime
                }

                # Apply variable substitution
                for var, value in variables.items():
                    prefix = prefix.replace(f"{{{var}}}", value)

                # Ensure we have a valid prefix
                if prefix:
                    # Stipulation proxy_prefix_format COMPLETELY REPLACES the path
                    # It's the full final path including the contract path
                    # e.g., prefix="/data-plane/{tenant_id}/v1/query/execute" -> use as-is
                    logger.debug(f"Path transformation: using complete prefix=/{prefix}")
                    return f"/{prefix}"
                else:
                    logger.warning(f"Empty prefix after processing for {category}:{version}")
            else:
                logger.warning(f"No proxy_prefix_format found for {category}:{version}")

            # Fallback - strip any existing version prefix from path
            clean_path = path
            # Remove common prefix patterns like /auth/v1, /v1, etc.
            import re

            clean_path = re.sub(r"^/[^/]+/v\d+", "", path)  # Remove /xxx/v1 prefix
            if not clean_path.startswith("/"):
                clean_path = "/" + clean_path
            fallback = f"/{category}/{version}{clean_path}"
            logger.debug(f"Using fallback prefix for {category}:{version}: {fallback}")
            return fallback

        except Exception as e:
            logger.warning(f"Failed to apply stipulation transformations for {category}:{version}: {e}")
            return f"/{category}/{version}{path}"

    def should_forbid_method(self, category: str, version: str, method: str) -> bool:
        """Check if method is forbidden by stipulation."""
        try:
            stipulation = self.governor.get_stipulation_for_contract(category, version)
            if stipulation and hasattr(stipulation, "forbid_methods"):
                return method.upper() in [m.upper() for m in stipulation.forbid_methods]
            return False
        except Exception:
            return False

    def get_metadata_block(self, category: str, version: str) -> Optional[Dict[str, Any]]:
        """Get stipulation metadata block."""
        try:
            stipulation = self.governor.get_stipulation_for_contract(category, version)
            if stipulation and hasattr(stipulation, "metadata_block"):
                # Safe: metadata_block is always a dict when present on a stipulation
                return cast(Dict[str, Any], stipulation.metadata_block)
            return None
        except Exception:
            return None

    def is_catalog_visible(self, category: str, version: str) -> bool:
        """Check if contract should be visible in catalog."""
        try:
            stipulation = self.governor.get_stipulation_for_contract(category, version)
            if stipulation and hasattr(stipulation, "catalog_default_visible"):
                # Safe: catalog_default_visible is always a bool on stipulation configs
                return cast(bool, stipulation.catalog_default_visible)
            return True  # Default to visible
        except Exception:
            return True

    def requires_scope_parameter(self, category: str, version: str) -> bool:
        """Check if stipulation requires scope parameters."""
        try:
            stipulation = self.governor.get_stipulation_for_contract(category, version)
            if stipulation and hasattr(stipulation, "requires_scope_parameter"):
                # Safe: requires_scope_parameter is always a bool on stipulation configs
                return cast(bool, stipulation.requires_scope_parameter)
            return False
        except Exception:
            return False

    def get_exposure_policy(self, category: str, version: str) -> Optional[str]:
        """Get stipulation exposure policy."""
        try:
            stipulation = self.governor.get_stipulation_for_contract(category, version)
            if stipulation and hasattr(stipulation, "exposure_policy"):
                return (
                    stipulation.exposure_policy.value
                    if hasattr(stipulation.exposure_policy, "value")
                    else str(stipulation.exposure_policy)
                )
            return None
        except Exception:
            return None

    def register_multi_tenant_stipulation(
        self, category: str, version: str, stipulation: MultiTenantStipulation
    ) -> None:
        """Register a multi-tenant stipulation with template support."""
        key = f"{category}:{version}"
        self._multi_tenant_stipulations[key] = stipulation

    def expand_contract_templates(self, category: str, version: str) -> List[ContractInstance]:
        """Expand contract templates into multiple instances."""
        key = f"{category}:{version}"
        mt_stipulation = self._multi_tenant_stipulations.get(key)

        if not mt_stipulation or not mt_stipulation.is_templated():
            return []

        # None guard: template is Optional[ContractTemplate]; is_templated() confirms it's not None
        if mt_stipulation.template is None:
            return []

        # Discover variable values if needed
        if mt_stipulation.discovery_sources:
            template_vars = mt_stipulation.template.get_template_variables()
            discovered = self.variable_discovery.discover_variables(template_vars)

            # Update template variables with discovered values
            for var_name, values in discovered.items():
                if var_name in mt_stipulation.template.variables:
                    mt_stipulation.template.variables[var_name].values.extend(values)

        # Safe: expand_template always returns List[ContractInstance]
        return cast(List[ContractInstance], self.template_expander.expand_template(mt_stipulation.template))

    def resolve_incoming_request(self, proxy_path: str) -> Optional[ContractInstance]:
        """Resolve incoming request to original contract instance."""
        # Safe: resolve_request always returns Optional[ContractInstance]
        return cast(Optional[ContractInstance], self.template_expander.resolve_request(proxy_path))

    def get_backend_url_for_request(self, proxy_path: str) -> Optional[str]:
        """Get backend URL for proxying request to data-plane."""
        instance = self.resolve_incoming_request(proxy_path)
        return instance.backend_url if instance else None
