"""
Default stipulation configurations for common API patterns.

This module provides pre-configured stipulations for tenant-scoped APIs,
global control-plane APIs, and other common patterns.
"""

from typing import Dict

from ..core.models import ExposurePolicy, StipulationConfig

# Export default stipulations for easy access
DEFAULT_STIPULATIONS = None

def get_default_stipulations() -> Dict[str, StipulationConfig]:
    """
    Get default stipulation configurations for common API patterns.

    Returns:
        Dictionary mapping stipulation keys to StipulationConfig objects
    """
    return {
        # Tenant-scoped Evidence Query API v1
        "evidence-query:v1": StipulationConfig(
            stipulation_id="evidence-query:v1",
            stipulation_version="1.0.0",
            exposure_policy=ExposurePolicy.TENANT_SCOPED,
            proxy_prefix_format="/tenant/{tenant_id}/evidence-query/v1",
            requires_scope_parameter=True,
            forbid_methods=["delete", "patch"],
            required_fields=["openapi", "info.title", "info.version", "paths"],
            require_openapi_major="3.",
            inject_metadata=True,
            metadata_block={
                "audit_note": "All requests brokered by control-plane and logged",
                "proxy_enforced": True,
                "platform": "Contract Stipulations System",
                "tenant_isolation": True,
                "data_classification": "tenant-scoped"
            },
            catalog_default_visible=True,
            extension_namespace="x-governance",
            enforce_version_alignment=True
        ),

        # Tenant-scoped Evidence Query API v2 (allows PATCH)
        "evidence-query:v2": StipulationConfig(
            stipulation_id="evidence-query:v2",
            stipulation_version="1.0.0",
            exposure_policy=ExposurePolicy.TENANT_SCOPED,
            proxy_prefix_format="/tenant/{tenant_id}/evidence-query/v2",
            requires_scope_parameter=True,
            forbid_methods=["delete"],  # v2 allows PATCH
            required_fields=["openapi", "info.title", "info.version", "paths"],
            require_openapi_major="3.",
            inject_metadata=True,
            metadata_block={
                "audit_note": "All requests brokered by control-plane and logged",
                "proxy_enforced": True,
                "platform": "Contract Stipulations System",
                "tenant_isolation": True,
                "data_classification": "tenant-scoped",
                "breaking_changes": "Allows PATCH operations"
            },
            catalog_default_visible=True,
            extension_namespace="x-governance",
            enforce_version_alignment=True
        ),

        # Global Control-Plane Authentication API
        "authentication:v1": StipulationConfig(
            stipulation_id="authentication:v1",
            stipulation_version="1.0.0",
            exposure_policy=ExposurePolicy.GLOBAL_CONTROL_PLANE,
            proxy_prefix_format="/auth/v1",
            requires_scope_parameter=False,
            forbid_methods=["delete"],
            required_fields=["openapi", "info.title", "info.version", "paths"],
            require_openapi_major="3.",
            inject_metadata=True,
            metadata_block={
                "audit_note": "Global authentication service - no tenant scoping",
                "proxy_enforced": True,
                "platform": "Contract Stipulations System",
                "tenant_isolation": False,
                "data_classification": "global-control-plane",
                "security_level": "high"
            },
            catalog_default_visible=True,
            extension_namespace="x-governance",
            enforce_version_alignment=True
        ),

        # Global Control-Plane Authorization API
        "authorization:v1": StipulationConfig(
            stipulation_id="authorization:v1",
            stipulation_version="1.0.0",
            exposure_policy=ExposurePolicy.GLOBAL_CONTROL_PLANE,
            proxy_prefix_format="/authz/v1",
            requires_scope_parameter=False,
            forbid_methods=["delete", "patch"],
            required_fields=["openapi", "info.title", "info.version", "paths"],
            require_openapi_major="3.",
            inject_metadata=True,
            metadata_block={
                "audit_note": "Global authorization service - policy enforcement",
                "proxy_enforced": True,
                "platform": "Contract Stipulations System",
                "tenant_isolation": False,
                "data_classification": "global-control-plane",
                "security_level": "critical"
            },
            catalog_default_visible=True,
            extension_namespace="x-governance",
            enforce_version_alignment=True
        ),

        # Tenant-scoped Policy Management API
        "policy-management:v1": StipulationConfig(
            stipulation_id="policy-management:v1",
            stipulation_version="1.0.0",
            exposure_policy=ExposurePolicy.TENANT_SCOPED,
            proxy_prefix_format="/tenant/{tenant_id}/policies/v1",
            requires_scope_parameter=True,
            forbid_methods=[],  # All methods allowed for policy management
            required_fields=["openapi", "info.title", "info.version", "paths"],
            require_openapi_major="3.",
            inject_metadata=True,
            metadata_block={
                "audit_note": "Tenant policy management - full CRUD operations",
                "proxy_enforced": True,
                "platform": "Contract Stipulations System",
                "tenant_isolation": True,
                "data_classification": "tenant-scoped",
                "operations_allowed": "full-crud"
            },
            catalog_default_visible=True,
            extension_namespace="x-governance",
            enforce_version_alignment=True
        ),

        # Private Internal API (not exposed in catalog)
        "internal-metrics:v1": StipulationConfig(
            stipulation_id="internal-metrics:v1",
            stipulation_version="1.0.0",
            exposure_policy=ExposurePolicy.PRIVATE,
            proxy_prefix_format="/internal/metrics/v1",
            requires_scope_parameter=False,
            forbid_methods=["post", "put", "patch", "delete"],  # Read-only
            required_fields=["openapi", "info.title", "info.version", "paths"],
            require_openapi_major="3.",
            inject_metadata=True,
            metadata_block={
                "audit_note": "Internal metrics API - read-only access",
                "proxy_enforced": True,
                "platform": "Contract Stipulations System",
                "tenant_isolation": False,
                "data_classification": "internal",
                "access_level": "private"
            },
            catalog_default_visible=False,  # Not visible in public catalog
            extension_namespace="x-governance",
            enforce_version_alignment=True
        ),

        # Multi-tenant Subscription API with scope parameter
        "subscription:v1": StipulationConfig(
            stipulation_id="subscription:v1",
            stipulation_version="1.0.0",
            exposure_policy=ExposurePolicy.TENANT_SCOPED,
            proxy_prefix_format="/tenant/{tenant_id}/subscriptions/v1",
            requires_scope_parameter=True,
            forbid_methods=["delete"],  # Prevent accidental subscription deletion
            required_fields=["openapi", "info.title", "info.version", "paths"],
            require_openapi_major="3.",
            inject_metadata=True,
            metadata_block={
                "audit_note": "Tenant subscription management - deletion restricted",
                "proxy_enforced": True,
                "platform": "Contract Stipulations System",
                "tenant_isolation": True,
                "data_classification": "tenant-scoped",
                "billing_impact": True
            },
            catalog_default_visible=True,
            extension_namespace="x-governance",
            enforce_version_alignment=True
        ),

        # Global Telemetry API
        "telemetry:v1": StipulationConfig(
            stipulation_id="telemetry:v1",
            stipulation_version="1.0.0",
            exposure_policy=ExposurePolicy.GLOBAL_CONTROL_PLANE,
            proxy_prefix_format="/telemetry/v1",
            requires_scope_parameter=False,
            forbid_methods=["delete", "patch"],
            required_fields=["openapi", "info.title", "info.version", "paths"],
            require_openapi_major="3.",
            inject_metadata=True,
            metadata_block={
                "audit_note": "Global telemetry collection - aggregated metrics",
                "proxy_enforced": True,
                "platform": "Contract Stipulations System",
                "tenant_isolation": False,
                "data_classification": "global-control-plane",
                "data_retention": "90_days"
            },
            catalog_default_visible=True,
            extension_namespace="x-governance",
            enforce_version_alignment=True
        )
    }


def get_stipulation_templates() -> Dict[str, Dict]:
    """
    Get stipulation templates for different API patterns.

    Returns:
        Dictionary mapping template names to template configurations
    """
    return {
        "tenant-scoped-crud": {
            "description": "Template for tenant-scoped APIs with full CRUD operations",
            "template": {
                "exposure_policy": "tenant-scoped",
                "proxy_prefix_format": "/tenant/{tenant_id}/{category}/v{major}",
                "requires_scope_parameter": True,
                "forbid_methods": [],
                "required_fields": ["openapi", "info.title", "info.version", "paths"],
                "require_openapi_major": "3.",
                "inject_metadata": True,
                "metadata_block": {
                    "audit_note": "Tenant-scoped API with full CRUD operations",
                    "proxy_enforced": True,
                    "platform": "Contract Stipulations System",
                    "tenant_isolation": True,
                    "data_classification": "tenant-scoped"
                },
                "catalog_default_visible": True,
                "extension_namespace": "x-governance",
                "enforce_version_alignment": True
            }
        },

        "tenant-scoped-readonly": {
            "description": "Template for tenant-scoped read-only APIs",
            "template": {
                "exposure_policy": "tenant-scoped",
                "proxy_prefix_format": "/tenant/{tenant_id}/{category}/v{major}",
                "requires_scope_parameter": True,
                "forbid_methods": ["post", "put", "patch", "delete"],
                "required_fields": ["openapi", "info.title", "info.version", "paths"],
                "require_openapi_major": "3.",
                "inject_metadata": True,
                "metadata_block": {
                    "audit_note": "Tenant-scoped read-only API",
                    "proxy_enforced": True,
                    "platform": "Contract Stipulations System",
                    "tenant_isolation": True,
                    "data_classification": "tenant-scoped",
                    "operations_allowed": "read-only"
                },
                "catalog_default_visible": True,
                "extension_namespace": "x-governance",
                "enforce_version_alignment": True
            }
        },

        "global-control-plane": {
            "description": "Template for global control-plane APIs",
            "template": {
                "exposure_policy": "global-control-plane",
                "proxy_prefix_format": "/{category}/v{major}",
                "requires_scope_parameter": False,
                "forbid_methods": ["delete"],
                "required_fields": ["openapi", "info.title", "info.version", "paths"],
                "require_openapi_major": "3.",
                "inject_metadata": True,
                "metadata_block": {
                    "audit_note": "Global control-plane API",
                    "proxy_enforced": True,
                    "platform": "Contract Stipulations System",
                    "tenant_isolation": False,
                    "data_classification": "global-control-plane"
                },
                "catalog_default_visible": True,
                "extension_namespace": "x-governance",
                "enforce_version_alignment": True
            }
        },

        "private-internal": {
            "description": "Template for private internal APIs",
            "template": {
                "exposure_policy": "private",
                "proxy_prefix_format": "/internal/{category}/v{major}",
                "requires_scope_parameter": False,
                "forbid_methods": ["post", "put", "patch", "delete"],
                "required_fields": ["openapi", "info.title", "info.version", "paths"],
                "require_openapi_major": "3.",
                "inject_metadata": True,
                "metadata_block": {
                    "audit_note": "Private internal API - not exposed in catalog",
                    "proxy_enforced": True,
                    "platform": "Contract Stipulations System",
                    "tenant_isolation": False,
                    "data_classification": "internal",
                    "access_level": "private"
                },
                "catalog_default_visible": False,
                "extension_namespace": "x-governance",
                "enforce_version_alignment": True
            }
        }
    }


# Initialize DEFAULT_STIPULATIONS
DEFAULT_STIPULATIONS = get_default_stipulations()
