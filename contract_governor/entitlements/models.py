"""
Data models for entitlement generation.

This module defines Pydantic models representing SpiceDB entitlement manifests,
operation-level entitlements, relationship tuples, and HTTP-to-action mappings.
"""

from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


class ActionType(str, Enum):
    """SpiceDB action types mapped from HTTP verbs."""
    READ = "read"
    WRITE = "write"
    DELETE = "delete"


class SpiceDBRelationship(BaseModel):
    """Represents a SpiceDB relationship tuple.

    UPDATED: Only 'dataplane' and 'action' relations are generated here.
    'allowed_context' relationships are created during DataPlane registration.
    """
    resource: str = Field(..., description="Resource identifier (e.g., 'api_operation:lexical-graph_prompts_status_get')")
    relation: str = Field(..., description="Relation name (e.g., 'dataplane', 'action')")
    subject: str = Field(..., description="Subject identifier (e.g., 'dataplane:PLACEHOLDER', 'action_type:read')")

    def to_spicedb_format(self) -> Dict[str, str]:
        """Convert to SpiceDB API format."""
        return {
            "resource": self.resource,
            "relation": self.relation,
            "subject": self.subject
        }


class OperationEntitlement(BaseModel):
    """Represents an API operation with its entitlement metadata.

    UPDATED: Removed spicedb_relationships - these are created by control-plane
    during DataPlane registration, not stored in the contract template.
    """
    operation_id: str = Field(..., description="Generated operation ID (path_method)")
    operation_id_snake_case: str = Field(..., description="Snake case version of operation_id for storage")
    path: str = Field(..., description="API path with {variables} preserved")
    path_variables: List[str] = Field(default_factory=list, description="List of path variables extracted from {}")
    query_parameters: List[str] = Field(default_factory=list, description="List of query parameter names from OpenAPI spec")
    query_parameter_examples: Dict[str, str] = Field(default_factory=dict, description="Example values for query parameters from OpenAPI spec")
    query_parameter_required: Dict[str, bool] = Field(default_factory=dict, description="Whether each query parameter is required")
    query_parameter_types: Dict[str, str] = Field(default_factory=dict, description="Type of each query parameter (string, integer, etc.)")
    body_parameters: List[str] = Field(default_factory=list, description="List of body parameter names from request body schema")
    body_parameter_examples: Dict[str, Any] = Field(default_factory=dict, description="Example values for body parameters")
    body_parameter_required: Dict[str, bool] = Field(default_factory=dict, description="Whether each body parameter is required")
    body_parameter_types: Dict[str, str] = Field(default_factory=dict, description="Type of each body parameter (string, array, boolean, etc.)")
    method: str = Field(..., description="HTTP method (GET, POST, etc.)")
    action: ActionType = Field(..., description="SpiceDB action type")
    tags: List[str] = Field(default_factory=list, description="OpenAPI tags")
    summary: Optional[str] = Field(None, description="Operation summary")
    description: Optional[str] = Field(None, description="Full operation description from OpenAPI")
    deprecated: bool = Field(False, description="Whether operation is deprecated")
    request_body_schema: Optional[Dict[str, Any]] = Field(None, description="Request body schema for POST/PUT operations")
    is_implemented: bool = Field(False, description="Whether operation has real implementation")
    cp_https: str = Field(..., description="Control plane HTTPS URL for router access")
    is_mock: bool = Field(True, description="Whether operation is mock-only")

    model_config = ConfigDict(use_enum_values=True)


class ContractManifest(BaseModel):
    """Contract manifest - pure API operation definition without authorization.

    This is a template that describes what operations exist in a contract.
    Authorization relationships (dataplane, security_context) are created by
    the control-plane during DataPlane registration.

    Renamed from EntitlementManifest to ContractManifest to reflect that this
    is just a contract definition, not authorization/entitlement data.
    """
    contract_name: str = Field(..., description="Contract/API name")
    contract_version: str = Field(..., description="Contract version")
    operations: List[OperationEntitlement] = Field(
        default_factory=list,
        description="List of operations"
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Additional metadata"
    )

    def to_spicedb_batch(self, dataplane_uuid: str, security_context_ids: List[str]) -> List[Dict[str, str]]:
        """
        Generate SpiceDB relationships for a specific DataPlane instance.

        This is called by the control-plane during DataPlane registration to create
        the actual authorization relationships.

        Args:
            dataplane_uuid: The actual DataPlane UUID
            security_context_ids: List of security context IDs for this DataPlane

        Returns:
            List of relationship tuples ready for SpiceDB batch write
        """
        relationships: List[Dict[str, str]] = []
        for op in self.operations:
            # Create dataplane relationship
            relationships.append({
                "resource": f"api_operation:{op.operation_id}",
                "relation": "dataplane",
                "subject": f"dataplane:{dataplane_uuid}"
            })
            # Create action relationship
            relationships.append({
                "resource": f"api_operation:{op.operation_id}",
                "relation": "action",
                "subject": f"action_type:{op.action}"
            })
            # Create allowed_context relationships for each security context
            for sc_id in security_context_ids:
                relationships.append({
                    "resource": f"api_operation:{op.operation_id}",
                    "relation": "allowed_context",
                    "subject": f"security_context:{sc_id}"
                })
        return relationships

    def get_implemented_operations(self) -> List[str]:
        """Return operation IDs for all implemented (non-mock) operations."""
        return [op.operation_id for op in self.operations if op.is_implemented]

    def get_mock_operations(self) -> List[str]:
        """Return operation IDs for all mock operations."""
        return [op.operation_id for op in self.operations if op.is_mock]

    def get_operations_by_action(self, action: ActionType) -> List[OperationEntitlement]:
        """Return operations filtered by action type."""
        return [op for op in self.operations if op.action == action]

    def get_operations_by_tag(self, tag: str) -> List[OperationEntitlement]:
        """Return operations filtered by tag."""
        return [op for op in self.operations if tag in op.tags]

    def to_summary(self) -> Dict[str, Any]:
        """Return a summary dictionary of the contract manifest."""
        return {
            "contract_name": self.contract_name,
            "contract_version": self.contract_version,
            "total_operations": len(self.operations),
            "implemented_operations": len(self.get_implemented_operations()),
            "mock_operations": len(self.get_mock_operations()),
            "read_operations": len(self.get_operations_by_action(ActionType.READ)),
            "write_operations": len(self.get_operations_by_action(ActionType.WRITE)),
            "delete_operations": len(self.get_operations_by_action(ActionType.DELETE)),
            "tags": list(set(tag for op in self.operations for tag in op.tags))
        }


# Backwards compatibility alias
EntitlementManifest = ContractManifest
