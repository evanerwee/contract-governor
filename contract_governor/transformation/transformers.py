"""
Transformer implementations for contract stipulation compliance.

This module contains the individual transformers that modify OpenAPI contracts
according to stipulation policies. Each transformer follows the Single
Responsibility Principle and focuses on one specific transformation aspect.
"""

import copy
from abc import ABC, abstractmethod
from typing import Any, Dict

from ..core.models import AuditMetadata, StipulationConfig, TransformContext
from .audit_utils import AuditHashGenerator, GovernanceMetadataBuilder
from .url_template_resolver import UrlTemplateResolver


class BaseTransformer(ABC):
    """
    Abstract base class for all contract transformers.

    Follows the Interface Segregation Principle by defining a minimal,
    focused interface that all transformers must implement.
    """

    @abstractmethod
    def transform(
        self, contract: Dict[str, Any], context: TransformContext, stipulation: StipulationConfig
    ) -> Dict[str, Any]:
        """
        Transform the contract according to the stipulation and context.

        Args:
            contract: The OpenAPI contract to transform
            context: The transformation context with parameters
            stipulation: The stipulation configuration to apply

        Returns:
            The transformed contract
        """
        pass

    def preview_transformation(
        self, contract: Dict[str, Any], context: TransformContext, stipulation: StipulationConfig
    ) -> Dict[str, Any]:
        """
        Preview what this transformer would do without actually transforming.

        Args:
            contract: The contract to preview transformation for
            context: The transformation context
            stipulation: The stipulation configuration

        Returns:
            Dictionary describing the planned transformation
        """
        return {"transformer": self.__class__.__name__, "changes": "No preview available"}


class URLRewriter(BaseTransformer):
    """
    Rewrites server URLs using stipulation-defined URL templates.

    Resolves ${VARIABLE} placeholders in server URL templates from environment variables.

    Follows Single Responsibility Principle - only handles URL rewriting.
    """

    def transform(
        self, contract: Dict[str, Any], context: TransformContext, stipulation: StipulationConfig
    ) -> Dict[str, Any]:
        """
        Rewrite server URLs using stipulation templates.

        Args:
            contract: The OpenAPI contract to transform
            context: The transformation context
            stipulation: The stipulation with server_urls templates

        Returns:
            Contract with resolved server URLs
        """
        transformed = copy.deepcopy(contract)

        # Resolve server URLs from stipulation templates
        if stipulation.server_urls:
            transformed["servers"] = UrlTemplateResolver.resolve_server_urls(stipulation.server_urls)
        else:
            # Fallback: build from gateway_base_url
            transformed["servers"] = [
                {"url": context.get_proxy_base_url(), "description": f"API endpoint for {context.category}"}
            ]

        return transformed

    def preview_transformation(
        self, contract: Dict[str, Any], context: TransformContext, stipulation: StipulationConfig
    ) -> Dict[str, Any]:
        """Preview the URL rewriting transformation."""
        current_servers = contract.get("servers", [])

        if stipulation.server_urls:
            try:
                new_servers = UrlTemplateResolver.resolve_server_urls(stipulation.server_urls)
                server_urls = [s["url"] for s in new_servers]

                return {
                    "transformer": "URLRewriter",
                    "current_servers": current_servers,
                    "new_servers": new_servers,
                    "changes": f"Will replace {len(current_servers)} server(s) with {len(new_servers)} URL(s): {', '.join(server_urls)}",
                }
            except Exception as e:
                return {"transformer": "URLRewriter", "error": str(e), "changes": f"Error resolving URLs: {str(e)}"}
        else:
            return {
                "transformer": "URLRewriter",
                "current_servers": current_servers,
                "changes": "Will use gateway_base_url as fallback",
            }


class MethodStripper(BaseTransformer):
    """
    Removes forbidden HTTP methods from contract paths.

    This transformer strips HTTP methods that are listed in the stipulation's
    forbid_methods configuration, ensuring only allowed methods are exposed.
    """

    def transform(
        self, contract: Dict[str, Any], context: TransformContext, stipulation: StipulationConfig
    ) -> Dict[str, Any]:
        """
        Remove forbidden HTTP methods from all paths in the contract.

        Args:
            contract: The OpenAPI contract to transform
            context: The transformation context
            stipulation: The stipulation with forbidden methods list

        Returns:
            Contract with forbidden methods removed
        """
        # Create a copy to avoid modifying the original
        transformed = copy.deepcopy(contract)

        # Get forbidden methods (normalize to lowercase)
        forbidden_methods = [method.lower() for method in stipulation.forbid_methods]

        if not forbidden_methods:
            return transformed

        # Process paths
        if "paths" in transformed:
            for path, path_obj in transformed["paths"].items():
                if isinstance(path_obj, dict):
                    # Remove forbidden methods from this path
                    methods_to_remove = []
                    for method in path_obj.keys():
                        if method.lower() in forbidden_methods:
                            methods_to_remove.append(method)

                    for method in methods_to_remove:
                        del path_obj[method]

        return transformed

    def preview_transformation(
        self, contract: Dict[str, Any], context: TransformContext, stipulation: StipulationConfig
    ) -> Dict[str, Any]:
        """Preview the method stripping transformation."""
        forbidden_methods = [method.lower() for method in stipulation.forbid_methods]
        methods_to_remove = []

        if "paths" in contract:
            for path, path_obj in contract["paths"].items():
                if isinstance(path_obj, dict):
                    for method in path_obj.keys():
                        if method.lower() in forbidden_methods:
                            methods_to_remove.append(f"{method.upper()} {path}")

        return {
            "transformer": "MethodStripper",
            "forbidden_methods": stipulation.forbid_methods,
            "methods_to_remove": methods_to_remove,
            "changes": (
                f"Will remove {len(methods_to_remove)} forbidden method(s)"
                if methods_to_remove
                else "No forbidden methods found"
            ),
        }


class AuditMetadataInjector(BaseTransformer):
    """
    Injects comprehensive audit and governance metadata into exposed contracts.

    This transformer adds audit metadata under the configured extension namespace
    to provide governance tracking and compliance information.
    """

    def transform(
        self, contract: Dict[str, Any], context: TransformContext, stipulation: StipulationConfig
    ) -> Dict[str, Any]:
        """
        Inject comprehensive audit metadata into the contract under the extension namespace.

        Args:
            contract: The OpenAPI contract to transform
            context: The transformation context with audit information
            stipulation: The stipulation with metadata configuration

        Returns:
            Contract with injected comprehensive audit metadata
        """
        # Create a copy to avoid modifying the original
        transformed = copy.deepcopy(contract)

        # Skip metadata injection if disabled
        if not stipulation.inject_metadata:
            return transformed

        # Create governance metadata builder
        metadata_builder = GovernanceMetadataBuilder(stipulation, context)

        # Build comprehensive audit block
        comprehensive_audit_block = metadata_builder.build_comprehensive_audit_block()

        # Inject metadata under the extension namespace
        if stipulation.extension_namespace:
            transformed[stipulation.extension_namespace] = comprehensive_audit_block

        # Also add to info section for visibility
        if "info" not in transformed:
            transformed["info"] = {}

        # Add governance information to info section
        if "x-governance" not in transformed["info"]:
            transformed["info"]["x-governance"] = metadata_builder.build_info_section_governance()

        # Generate and store contract hash for integrity verification
        contract_hash = AuditHashGenerator.generate_contract_hash(transformed, exclude_extensions=True)
        transformed[stipulation.extension_namespace]["audit_integrity"]["contract_hash"] = contract_hash

        return transformed

    def _create_audit_metadata(self, context: TransformContext, stipulation: StipulationConfig) -> AuditMetadata:
        """
        Create comprehensive audit metadata for the contract.

        Args:
            context: The transformation context
            stipulation: The stipulation configuration

        Returns:
            AuditMetadata object with complete audit information
        """
        # Create base audit metadata
        audit_metadata = AuditMetadata(
            capability_category=context.category,
            api_major_version=context.api_major_version,
            contract_version=context.contract_version,
            stipulation_id=stipulation.stipulation_id,
            stipulation_version=stipulation.stipulation_version,
            stipulation_hash=stipulation.get_stipulation_hash(),
            proxy_enforced=True,
            exposed_at=context.transformation_timestamp,
            exposed_by=context.source_service,
            audit_note=stipulation.metadata_block.get("audit_note", "Contract governed by stipulations"),
            compliance_status="compliant",
            governance_version="1.0.0",
            access_level=context.target_audience,
        )

        # Add tenant scope if applicable
        if context.has_scope_parameter("tenant_id"):
            audit_metadata.tenant_scope = context.get_scope_parameter("tenant_id")

        # Add custom metadata from stipulation
        for key, value in stipulation.metadata_block.items():
            if key != "audit_note":  # Already handled above
                audit_metadata.add_custom_metadata(key, value)

        # Add context metadata overrides
        for key, value in context.metadata_overrides.items():
            audit_metadata.add_custom_metadata(key, value)

        return audit_metadata

    def preview_transformation(
        self, contract: Dict[str, Any], context: TransformContext, stipulation: StipulationConfig
    ) -> Dict[str, Any]:
        """Preview the comprehensive audit metadata injection transformation."""
        if not stipulation.inject_metadata:
            return {"transformer": "AuditMetadataInjector", "changes": "Metadata injection is disabled"}

        metadata_builder = GovernanceMetadataBuilder(stipulation, context)
        comprehensive_audit_block = metadata_builder.build_comprehensive_audit_block()
        stipulation_hash = AuditHashGenerator.generate_stipulation_hash(stipulation)

        return {
            "transformer": "AuditMetadataInjector",
            "extension_namespace": stipulation.extension_namespace,
            "audit_metadata_keys": list(comprehensive_audit_block.keys()),
            "stipulation_hash": stipulation_hash,
            "governance_framework": comprehensive_audit_block.get("governance_framework", {}),
            "audit_integrity": comprehensive_audit_block.get("audit_integrity", {}),
            "changes": f"Will inject comprehensive audit metadata under {stipulation.extension_namespace}",
        }


class SecurityEnforcer(BaseTransformer):
    """
    Applies security transformations to contracts.

    This transformer can add security schemes, modify security requirements,
    and ensure security best practices are applied to exposed contracts.
    """

    def transform(
        self, contract: Dict[str, Any], context: TransformContext, stipulation: StipulationConfig
    ) -> Dict[str, Any]:
        """
        Apply security transformations to the contract.

        Args:
            contract: The OpenAPI contract to transform
            context: The transformation context
            stipulation: The stipulation configuration

        Returns:
            Contract with security transformations applied
        """
        # Create a copy to avoid modifying the original
        transformed = copy.deepcopy(contract)

        # Add security schemes if not present
        if "components" not in transformed:
            transformed["components"] = {}

        if "securitySchemes" not in transformed["components"]:
            transformed["components"]["securitySchemes"] = {}

        # Add bearer token security scheme for tenant-scoped APIs
        if stipulation.exposure_policy.value == "tenant-scoped":
            transformed["components"]["securitySchemes"]["bearerAuth"] = {
                "type": "http",
                "scheme": "bearer",
                "bearerFormat": "JWT",
                "description": "Bearer token authentication required for tenant-scoped access",
            }

            # Add security requirement to all operations if not present
            if "security" not in transformed:
                transformed["security"] = [{"bearerAuth": []}]

        return transformed

    def preview_transformation(
        self, contract: Dict[str, Any], context: TransformContext, stipulation: StipulationConfig
    ) -> Dict[str, Any]:
        """Preview the security enforcement transformation."""
        changes = []

        if stipulation.exposure_policy.value == "tenant-scoped":
            has_security = "components" in contract and "securitySchemes" in contract.get("components", {})
            if not has_security:
                changes.append("Will add bearer token security scheme")

            if "security" not in contract:
                changes.append("Will add security requirements")

        return {
            "transformer": "SecurityEnforcer",
            "exposure_policy": stipulation.exposure_policy.value,
            "changes": "; ".join(changes) if changes else "No security changes needed",
        }
