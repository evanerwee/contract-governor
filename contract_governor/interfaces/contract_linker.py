"""
Abstract interface for contract-stipulation linking strategies.

This module defines the ContractLinker protocol for resolving which stipulation
policy applies to a given contract based on its file path or metadata.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, Optional

from ..core.models import StipulationConfig


class ContractLinker(ABC):
    """Abstract interface for linking contracts to stipulations."""

    @abstractmethod
    def find_stipulation_by_path(self, contract_path: str) -> Optional[StipulationConfig]:
        """Find stipulation based on contract file path."""
        pass

    @abstractmethod
    def find_stipulation_by_spec(self, openapi_spec: Dict[str, Any]) -> Optional[StipulationConfig]:
        """Find stipulation based on OpenAPI spec metadata."""
        pass
