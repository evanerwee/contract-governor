"""
Focused interfaces for serving concerns implementing Interface Segregation Principle.

These interfaces separate serving concerns so that clients only depend on
the specific serving capabilities they need, not on unused methods.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from ..core.models import ExposedContractRecord


class CatalogProvider(ABC):
    """
    Interface focused solely on catalog data provision.

    Clients that only need catalog data don't depend on HTTP serving
    or documentation rendering methods.
    """

    @abstractmethod
    def get_catalog_contracts(self, filters: Optional[Dict[str, Any]] = None) -> List[ExposedContractRecord]:
        """Get contracts for catalog display."""
        pass

    @abstractmethod
    def get_contract_summary(self, category: str, api_major: str) -> Optional[Dict[str, Any]]:
        """Get summary information for a specific contract."""
        pass

    @abstractmethod
    def filter_visible_contracts(self, contracts: List[ExposedContractRecord]) -> List[ExposedContractRecord]:
        """Filter contracts based on visibility settings."""
        pass


class ContractProvider(ABC):
    """
    Interface focused solely on individual contract provision.

    Clients that only need contract data don't depend on catalog
    or documentation methods.
    """

    @abstractmethod
    def get_contract_spec(self, category: str, api_major: str) -> Optional[Dict[str, Any]]:
        """Get OpenAPI specification for a specific contract."""
        pass

    @abstractmethod
    def get_contract_metadata(self, category: str, api_major: str) -> Optional[Dict[str, Any]]:
        """Get metadata for a specific contract."""
        pass

    @abstractmethod
    def is_contract_available(self, category: str, api_major: str) -> bool:
        """Check if a contract is available for serving."""
        pass


class HealthProvider(ABC):
    """
    Interface focused solely on health and readiness checks.

    Clients that only need health checks don't depend on contract
    or catalog serving methods.
    """

    @abstractmethod
    def check_health(self) -> Dict[str, Any]:
        """Perform health check and return status."""
        pass

    @abstractmethod
    def check_readiness(self) -> Dict[str, Any]:
        """Perform readiness check and return status."""
        pass

    @abstractmethod
    def get_service_info(self) -> Dict[str, Any]:
        """Get service information for monitoring."""
        pass
