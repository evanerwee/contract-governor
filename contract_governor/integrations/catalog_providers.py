"""
SOLID implementations of catalog and contract providers for Contract-Governor.

These providers implement the interfaces defined in serving_concerns and follow
the Single Responsibility Principle by delegating to ContractGovernor domain logic.
"""

from typing import Any, Dict, List, Optional, cast

from ..core.models import ExposedContractRecord
from ..interfaces.serving_concerns import CatalogProvider, ContractProvider, HealthProvider


class ContractGovernorCatalogProvider(CatalogProvider):
    """
    Catalog provider that delegates to ContractGovernor for contract listing.

    Single Responsibility: Provide catalog data from ContractGovernor domain.
    """

    def __init__(self, contract_governor):
        """Initialize catalog provider with a ContractGovernor instance."""
        self.contract_governor = contract_governor

    def get_catalog_contracts(self, filters: Optional[Dict[str, Any]] = None) -> List[ExposedContractRecord]:
        """Get contracts from ContractGovernor with optional filtering."""
        # Safe cast: contract_governor.list_exposed_contracts() is declared to return
        # List[ExposedContractRecord] in both ContractGovernor and ContractRegistry interface;
        # mypy infers Any only because __init__ param is untyped.
        return cast(List[ExposedContractRecord], self.contract_governor.list_exposed_contracts(filters))

    def filter_visible_contracts(self, contracts: List[ExposedContractRecord]) -> List[ExposedContractRecord]:
        """Filter contracts to only visible ones."""
        return [c for c in contracts if c.catalog_visible]

    def get_contract_summary(self, category: str, api_major: str) -> Optional[Dict[str, Any]]:
        """Get summary information for a specific contract."""
        contract = self.contract_governor.get_exposed_contract(category, api_major)
        if not contract:
            return None

        return {
            "category": contract.category,
            "api_major_version": contract.api_major_version,
            "title": contract.get_contract_title(),
            "description": contract.get_contract_description(),
            "version": contract.contract_version
        }


class ContractGovernorContractProvider(ContractProvider):
    """
    Contract provider that delegates to ContractGovernor for individual contract access.

    Single Responsibility: Provide individual contract data from ContractGovernor domain.
    """

    def __init__(self, contract_governor):
        """Initialize contract provider with a ContractGovernor instance."""
        self.contract_governor = contract_governor

    def is_contract_available(self, category: str, api_major: str) -> bool:
        """Check if a specific contract is available."""
        return self.contract_governor.get_exposed_contract(category, api_major) is not None

    def get_contract_spec(self, category: str, api_major: str) -> Optional[Dict[str, Any]]:
        """Get OpenAPI spec for a specific contract."""
        contract = self.contract_governor.get_exposed_contract(category, api_major)
        return contract.exposed_openapi_spec if contract else None

    def get_contract_metadata(self, category: str, api_major: str) -> Optional[Dict[str, Any]]:
        """Get metadata for a specific contract."""
        contract = self.contract_governor.get_exposed_contract(category, api_major)
        if not contract:
            return None

        return {
            "category": contract.category,
            "api_major_version": contract.api_major_version,
            "contract_version": contract.contract_version,
            "source_service": contract.source_service,
            "stipulation_applied": contract.stipulation_applied,
            "exposed_at": contract.exposed_at.isoformat() if contract.exposed_at else None,
            "proxy_prefix": contract.proxy_prefix
        }


class BasicHealthProvider(HealthProvider):
    """
    Basic health provider for Contract-Governor services.

    Single Responsibility: Provide health status information.
    """

    def check_health(self) -> Dict[str, Any]:
        """Basic health check."""
        return {"status": "healthy"}

    def check_readiness(self) -> Dict[str, Any]:
        """Basic readiness check."""
        return {"status": "ready"}

    def get_service_info(self) -> Dict[str, Any]:
        """Basic service information."""
        return {
            "service": "contract-governor",
            "version": "1.0.0",
            "description": "Contract governance and catalog service"
        }
