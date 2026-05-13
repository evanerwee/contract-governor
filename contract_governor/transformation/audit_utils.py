"""
Audit utilities for contract transformation and governance tracking.

This module provides utilities for generating audit hashes, verifying
stipulation integrity, and managing governance metadata for contracts.
"""

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Dict

from ..core.models import AuditMetadata, StipulationConfig, TransformContext


class AuditHashGenerator:
    """
    Generates and verifies audit hashes for non-repudiation tracking.

    This class provides methods to create cryptographic hashes of stipulations
    and audit metadata to ensure integrity and non-repudiation of governance
    decisions.
    """

    @staticmethod
    def generate_stipulation_hash(stipulation: StipulationConfig) -> str:
        """
        Generate a SHA-256 hash of the stipulation configuration.

        This hash can be used for non-repudiation tracking to prove
        which exact stipulation was applied to a contract.

        Args:
            stipulation: The stipulation configuration to hash

        Returns:
            SHA-256 hash of the stipulation as a hex string
        """
        return stipulation.get_stipulation_hash()

    @staticmethod
    def generate_audit_metadata_hash(audit_metadata: AuditMetadata) -> str:
        """
        Generate a SHA-256 hash of the audit metadata.

        This hash can be used to verify the integrity of audit metadata
        and detect any tampering with governance information.

        Args:
            audit_metadata: The audit metadata to hash

        Returns:
            SHA-256 hash of the audit metadata as a hex string
        """
        return audit_metadata.get_audit_hash()

    @staticmethod
    def generate_contract_hash(contract: Dict[str, Any], exclude_extensions: bool = True) -> str:
        """
        Generate a SHA-256 hash of the contract content.

        This hash can be used to verify contract integrity and detect
        unauthorized modifications to exposed contracts.

        Args:
            contract: The OpenAPI contract to hash
            exclude_extensions: Whether to exclude extension fields from hash

        Returns:
            SHA-256 hash of the contract as a hex string
        """
        # Create a copy for hashing
        contract_copy = contract.copy()

        # Remove extension fields if requested
        if exclude_extensions:
            contract_copy = {k: v for k, v in contract_copy.items() if not k.startswith("x-")}

        # Remove transformation metadata that changes with each transformation
        contract_copy.pop("x-transformation-metadata", None)

        # Create deterministic JSON and hash it
        contract_json = json.dumps(contract_copy, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(contract_json.encode()).hexdigest()

    @staticmethod
    def verify_stipulation_hash(stipulation: StipulationConfig, expected_hash: str) -> bool:
        """
        Verify that a stipulation matches the expected hash.

        Args:
            stipulation: The stipulation to verify
            expected_hash: The expected hash value

        Returns:
            True if the stipulation hash matches, False otherwise
        """
        actual_hash = AuditHashGenerator.generate_stipulation_hash(stipulation)
        return actual_hash == expected_hash

    @staticmethod
    def create_audit_trail_entry(
        contract: Dict[str, Any],
        stipulation: StipulationConfig,
        context: TransformContext,
        transformation_result: str = "success",
    ) -> Dict[str, Any]:
        """
        Create a comprehensive audit trail entry for a contract transformation.

        Args:
            contract: The transformed contract
            stipulation: The stipulation that was applied
            context: The transformation context
            transformation_result: The result of the transformation

        Returns:
            Dictionary containing complete audit trail information
        """
        return {
            "audit_trail_id": f"{context.category}:{context.api_major_version}:{context.transformation_timestamp.isoformat()}",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "transformation_result": transformation_result,
            "contract_hash": AuditHashGenerator.generate_contract_hash(contract),
            "stipulation_hash": AuditHashGenerator.generate_stipulation_hash(stipulation),
            "stipulation_id": stipulation.stipulation_id,
            "stipulation_version": stipulation.stipulation_version,
            "category": context.category,
            "api_major_version": context.api_major_version,
            "contract_version": context.contract_version,
            "source_service": context.source_service,
            "gateway_base_url": context.gateway_base_url,
            "target_audience": context.target_audience,
            "scope_parameters": context.scope_parameters.copy(),
            "environment": context.environment,
            "request_id": context.request_id,
        }


class GovernanceMetadataBuilder:
    """
    Builds comprehensive governance metadata for contract exposure.

    This class creates structured governance metadata that provides
    complete audit trails and compliance information for exposed contracts.
    """

    def __init__(self, stipulation: StipulationConfig, context: TransformContext):
        """
        Initialize the governance metadata builder.

        Args:
            stipulation: The stipulation configuration
            context: The transformation context
        """
        self.stipulation = stipulation
        self.context = context

    def build_comprehensive_audit_block(self) -> Dict[str, Any]:
        """
        Build a comprehensive audit block with all governance information.

        Returns:
            Dictionary containing complete audit and governance metadata
        """
        # Create base audit metadata
        audit_metadata = AuditMetadata(
            capability_category=self.context.category,
            api_major_version=self.context.api_major_version,
            contract_version=self.context.contract_version,
            stipulation_id=self.stipulation.stipulation_id,
            stipulation_version=self.stipulation.stipulation_version,
            stipulation_hash=self.stipulation.get_stipulation_hash(),
            proxy_enforced=True,
            exposed_at=self.context.transformation_timestamp,
            exposed_by=self.context.source_service,
            audit_note=self.stipulation.metadata_block.get("audit_note", "Contract governed by stipulations"),
            compliance_status="compliant",
            governance_version="1.0.0",
            access_level=self.context.target_audience,
        )

        # Add tenant scope if applicable
        if self.context.has_scope_parameter("tenant_id"):
            audit_metadata.tenant_scope = self.context.get_scope_parameter("tenant_id")

        # Add custom metadata from stipulation
        for key, value in self.stipulation.metadata_block.items():
            if key != "audit_note":  # Already handled above
                audit_metadata.add_custom_metadata(key, value)

        # Add context metadata overrides
        for key, value in self.context.metadata_overrides.items():
            audit_metadata.add_custom_metadata(key, value)

        # Build comprehensive audit block
        audit_block = audit_metadata.to_dict()

        # Add additional governance information
        audit_block.update(
            {
                "governance_framework": {
                    "name": "Contract Stipulations System",
                    "version": "1.0.0",
                    "specification": "https://github.com/contract-stipulations/spec",
                },
                "transformation_metadata": {
                    "transformation_id": f"{self.context.category}:{self.context.api_major_version}:{self.context.transformation_timestamp.isoformat()}",
                    "gateway_base_url": self.context.gateway_base_url,
                    "proxy_prefix_format": self.stipulation.proxy_prefix_format,
                    "exposure_policy": (
                        self.stipulation.exposure_policy.value
                        if hasattr(self.stipulation.exposure_policy, "value")
                        else self.stipulation.exposure_policy
                    ),
                    "requires_scope_parameter": self.stipulation.requires_scope_parameter,
                },
                "compliance_metadata": {
                    "validation_passed": True,
                    "forbidden_methods_stripped": self.stipulation.forbid_methods,
                    "required_fields_verified": self.stipulation.required_fields,
                    "openapi_version_requirement": self.stipulation.require_openapi_major,
                    "version_alignment_enforced": self.stipulation.enforce_version_alignment,
                },
                "audit_integrity": {
                    "audit_metadata_hash": audit_metadata.get_audit_hash(),
                    "stipulation_hash": self.stipulation.get_stipulation_hash(),
                    "hash_algorithm": "SHA-256",
                    "hash_timestamp": datetime.now(timezone.utc).isoformat(),
                },
            }
        )

        return audit_block

    def build_info_section_governance(self) -> Dict[str, Any]:
        """
        Build governance metadata for the OpenAPI info section.

        Returns:
            Dictionary containing governance metadata for the info section
        """
        return {
            "stipulation_id": self.stipulation.stipulation_id,
            "compliance_status": "compliant",
            "proxy_enforced": True,
            "governance_framework": "Contract Stipulations System v1.0.0",
            "audit_timestamp": self.context.transformation_timestamp.isoformat(),
            "exposure_policy": (
                self.stipulation.exposure_policy.value
                if hasattr(self.stipulation.exposure_policy, "value")
                else self.stipulation.exposure_policy
            ),
        }

    def get_extension_namespace(self) -> str:
        """
        Get the extension namespace for metadata injection.

        Returns:
            The extension namespace string
        """
        return self.stipulation.extension_namespace

    def should_inject_metadata(self) -> bool:
        """
        Check if metadata should be injected based on stipulation configuration.

        Returns:
            True if metadata should be injected, False otherwise
        """
        return self.stipulation.inject_metadata
