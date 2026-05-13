"""
In-memory implementation of the Contract Registry.

This implementation provides thread-safe storage for raw and exposed contracts
with strict separation to prevent accidental exposure of internal contracts.
"""

import threading
from typing import Any, Dict, List, Optional

from ..interfaces.contract_registry import ContractRegistry
from .models import ExposedContractRecord, RawContractRecord


class InMemoryContractRegistry(ContractRegistry):
    """
    Thread-safe in-memory implementation of the Contract Registry.

    Maintains strict separation between raw contracts (never exposed)
    and exposed contracts (safe for client access).
    """

    def __init__(self):
        """Initialize the registry with separate storage for raw and exposed contracts."""
        self._raw_contracts: Dict[str, RawContractRecord] = {}
        self._exposed_contracts: Dict[str, ExposedContractRecord] = {}
        self._lock = threading.RLock()  # Reentrant lock for thread safety

    def store_raw_contract(self, record: RawContractRecord) -> None:
        """
        Store a raw contract record from a backend service.

        Args:
            record: The raw contract record to store
        """
        if not isinstance(record, RawContractRecord):
            raise TypeError("record must be a RawContractRecord instance")

        key = self._make_key(record.category, record.api_major_version, record.source_service)

        with self._lock:
            self._raw_contracts[key] = record

    def get_raw_contract(
        self, category: str, api_major: str, source_service: str | None = None
    ) -> Optional[RawContractRecord]:
        """
        Retrieve a raw contract record for internal processing only.

        Args:
            category: API category
            api_major: API major version
            source_service: Source service name for unique identification

        Returns:
            Raw contract record if found, None otherwise
        """
        key = self._make_key(category, api_major, source_service)

        with self._lock:
            return self._raw_contracts.get(key)

    def list_raw_contracts(self) -> List[RawContractRecord]:
        """
        List all raw contracts for internal processing only.

        Returns:
            List of all raw contract records
        """
        with self._lock:
            return list(self._raw_contracts.values())

    def store_exposed_contract(self, record: ExposedContractRecord) -> None:
        """
        Store an exposed contract record that is safe for client access.

        Args:
            record: The exposed contract record to store
        """
        if not isinstance(record, ExposedContractRecord):
            raise TypeError("record must be an ExposedContractRecord instance")

        key = self._make_key(record.category, record.api_major_version, record.source_service)

        with self._lock:
            self._exposed_contracts[key] = record

    def get_exposed_contract(
        self, category: str, api_major: str, source_service: str | None = None
    ) -> Optional[ExposedContractRecord]:
        """
        Retrieve an exposed contract record for client serving.

        Args:
            category: API category
            api_major: API major version
            source_service: Source service name for unique identification

        Returns:
            Exposed contract record if found, None otherwise
        """
        key = self._make_key(category, api_major, source_service)

        with self._lock:
            return self._exposed_contracts.get(key)

    def list_exposed_contracts(self, filters: Optional[Dict[str, Any]] = None) -> List[ExposedContractRecord]:
        """
        List exposed contracts with optional filtering.

        Args:
            filters: Optional filtering criteria

        Returns:
            List of exposed contract records matching the filters
        """
        with self._lock:
            contracts = list(self._exposed_contracts.values())

        if not filters:
            return contracts

        # Apply filters
        filtered_contracts = []
        for contract in contracts:
            if self._matches_filters(contract, filters):
                filtered_contracts.append(contract)

        return filtered_contracts

    def remove_raw_contract(self, category: str, api_major: str) -> bool:
        """
        Remove a raw contract record.

        Args:
            category: API category
            api_major: API major version

        Returns:
            True if removed, False if not found
        """
        key = self._make_key(category, api_major)

        with self._lock:
            if key in self._raw_contracts:
                del self._raw_contracts[key]
                return True
            return False

    def remove_exposed_contract(self, category: str, api_major: str) -> bool:
        """
        Remove an exposed contract record.

        Args:
            category: API category
            api_major: API major version

        Returns:
            True if removed, False if not found
        """
        key = self._make_key(category, api_major)

        with self._lock:
            if key in self._exposed_contracts:
                del self._exposed_contracts[key]
                return True
            return False

    def clear_all_contracts(self) -> None:
        """
        Clear all contracts (both raw and exposed) from the registry.
        """
        with self._lock:
            self._raw_contracts.clear()
            self._exposed_contracts.clear()

    def get_contract_count(self) -> Dict[str, int]:
        """
        Get count of contracts by type.

        Returns:
            Dictionary with 'raw' and 'exposed' counts
        """
        with self._lock:
            return {"raw": len(self._raw_contracts), "exposed": len(self._exposed_contracts)}

    def _make_key(self, category: str, api_major: str, source_service: str | None = None) -> str:
        """Create a registry key from category, API major version, and optionally source service."""
        if not category or not api_major:
            raise ValueError("Both category and api_major must be non-empty strings")
        if source_service:
            return f"{category}:{api_major}:{source_service}"
        return f"{category}:{api_major}"

    def _matches_filters(self, contract: ExposedContractRecord, filters: Dict[str, Any]) -> bool:
        """
        Check if a contract matches the given filters.

        Args:
            contract: The contract to check
            filters: Filter criteria

        Returns:
            True if contract matches all filters
        """
        for filter_key, filter_value in filters.items():
            if filter_key == "api_major_filter" and filter_value:
                if contract.api_major_version != filter_value:
                    return False
            elif filter_key == "category_filter" and filter_value:
                if contract.category != filter_value:
                    return False
            elif filter_key == "catalog_visible" and filter_value is not None:
                if contract.catalog_visible != filter_value:
                    return False
            elif filter_key == "source_service" and filter_value:
                if contract.source_service != filter_value:
                    return False
            elif filter_key == "tags" and filter_value:
                # Check if contract has any of the specified tags
                if not any(tag in contract.tags for tag in filter_value):
                    return False

        return True

    def get_registry_stats(self) -> Dict[str, Any]:
        """
        Get detailed statistics about the registry contents.

        Returns:
            Dictionary with registry statistics
        """
        with self._lock:
            raw_contracts = list(self._raw_contracts.values())
            exposed_contracts = list(self._exposed_contracts.values())

        # Analyze raw contracts
        raw_categories = set(c.category for c in raw_contracts)
        raw_services = set(c.source_service for c in raw_contracts)

        # Analyze exposed contracts
        exposed_categories = set(c.category for c in exposed_contracts)
        exposed_services = set(c.source_service for c in exposed_contracts)
        visible_contracts = [c for c in exposed_contracts if c.catalog_visible]

        return {
            "raw_contracts": {
                "count": len(raw_contracts),
                "categories": list(raw_categories),
                "source_services": list(raw_services),
            },
            "exposed_contracts": {
                "count": len(exposed_contracts),
                "categories": list(exposed_categories),
                "source_services": list(exposed_services),
                "catalog_visible_count": len(visible_contracts),
            },
            "coverage": {
                "categories_with_exposed": len(exposed_categories),
                "categories_raw_only": len(raw_categories - exposed_categories),
            },
        }
