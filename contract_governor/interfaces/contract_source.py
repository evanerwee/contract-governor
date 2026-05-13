"""
Abstract interface for contract source implementations.

This module defines the ContractSource protocol for loading OpenAPI contracts
from various backends (local filesystem, S3, etc.) in a uniform manner.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List


class ContractSource(ABC):
    """Abstract interface for loading OpenAPI contracts from various sources."""

    @abstractmethod
    def load_contracts(self) -> List[Dict[str, Any]]:
        """Load all contracts from the source.

        Returns:
            List of dicts with keys: contract, category, api_major, source_service, contract_file_path
        """
        pass
