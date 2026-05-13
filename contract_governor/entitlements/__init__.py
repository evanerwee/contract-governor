"""
Entitlement generation module for SpiceDB integration.

This module provides functionality to generate SpiceDB entitlement manifests
from OpenAPI contracts, enabling automatic authorization setup during
dataplane registration.
"""

from .entitlement_generator import EntitlementGenerator
from .models import ActionType, EntitlementManifest, OperationEntitlement, SpiceDBRelationship

__all__ = [
    "EntitlementGenerator",
    "EntitlementManifest",
    "OperationEntitlement",
    "SpiceDBRelationship",
    "ActionType"
]
