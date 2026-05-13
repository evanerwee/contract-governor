"""
Abstract interface for contract registry implementations.

This interface implements the Dependency Inversion Principle by allowing
the Contract Governor to depend on this abstraction rather than concrete
storage implementations.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from ..core.models import ExposedContractRecord, RawContractRecord


class ContractRegistry(ABC):
    """
    Abstract interface for contract storage with strict raw/exposed separation.

    This interface ensures that raw contracts (from backend services) are never
    accidentally exposed to clients, and only validated, transformed contracts
    are available for client access.
    """

    @abstractmethod
    def store_raw_contract(self, record: RawContractRecord) -> None:
        """
        Store a raw contract record from a backend service.

        Raw contracts are NEVER exposed to clients and contain internal URLs
        and potentially unsafe methods.

        Args:
            record: The raw contract record to store
        """
        pass

    @abstractmethod
    def get_raw_contract(self, category: str, api_major: str) -> Optional[RawContractRecord]:
        """
        Retrieve a raw contract record for internal processing only.

        Args:
            category: API category
            api_major: API major version

        Returns:
            Raw contract record if found, None otherwise
        """
        pass

    @abstractmethod
    def list_raw_contracts(self) -> List[RawContractRecord]:
        """
        List all raw contracts for internal processing only.

        Returns:
            List of all raw contract records
        """
        pass

    @abstractmethod
    def store_exposed_contract(self, record: ExposedContractRecord) -> None:
        """
        Store an exposed contract record that is safe for client access.

        Exposed contracts have been validated, transformed, and stamped with
        audit metadata. They are the ONLY contracts that should be served to clients.

        Args:
            record: The exposed contract record to store
        """
        pass

    @abstractmethod
    def get_exposed_contract(self, category: str, api_major: str) -> Optional[ExposedContractRecord]:
        """
        Retrieve an exposed contract record for client serving.

        Args:
            category: API category
            api_major: API major version

        Returns:
            Exposed contract record if found, None otherwise
        """
        pass

    @abstractmethod
    def list_exposed_contracts(self, filters: Optional[Dict[str, Any]] = None) -> List[ExposedContractRecord]:
        """
        List exposed contracts with optional filtering.

        This is the ONLY method that should be used for client-facing catalogs.

        Args:
            filters: Optional filtering criteria

        Returns:
            List of exposed contract records matching the filters
        """
        pass

    @abstractmethod
    def remove_raw_contract(self, category: str, api_major: str) -> bool:
        """
        Remove a raw contract record.

        Args:
            category: API category
            api_major: API major version

        Returns:
            True if removed, False if not found
        """
        pass

    @abstractmethod
    def remove_exposed_contract(self, category: str, api_major: str) -> bool:
        """
        Remove an exposed contract record.

        Args:
            category: API category
            api_major: API major version

        Returns:
            True if removed, False if not found
        """
        pass

    @abstractmethod
    def clear_all_contracts(self) -> None:
        """
        Clear all contracts (both raw and exposed) from the registry.

        This is primarily for testing purposes.
        """
        pass

    @abstractmethod
    def get_contract_count(self) -> Dict[str, int]:
        """
        Get count of contracts by type.

        Returns:
            Dictionary with 'raw' and 'exposed' counts
        """
        pass
