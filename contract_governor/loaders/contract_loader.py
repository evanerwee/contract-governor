"""
Contract loading from various sources with stipulation linking.

This module provides the ContractLoader class which reads OpenAPI contract
files from the filesystem, parses them, and links each contract to its
applicable stipulation policy.
"""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional, cast

import yaml

from ..core.models import RawContractRecord, StipulationConfig
from ..interfaces.contract_linker import ContractLinker


class ContractLoader:
    """Loads contracts and links them to stipulations."""

    def __init__(self, linker: ContractLinker):
        """Initialize contract loader with a contract-to-stipulation linker."""
        self.linker = linker

    def load_contract(self, file_path: str) -> tuple[RawContractRecord, Optional[StipulationConfig]]:
        """
        Load contract and find its stipulation.

        Returns:
            Tuple of (RawContractRecord, StipulationConfig or None)
        """
        # Load OpenAPI spec
        spec = self._load_spec_file(file_path)

        # Parse path to extract category and version
        category, version = self._parse_path(file_path)

        # Create raw contract record
        contract = RawContractRecord(
            category=category,
            api_major_version=version,
            contract_version=spec.get("info", {}).get("version", "1.0.0"),
            source_service=spec.get("info", {}).get("title", "Unknown"),
            raw_openapi_spec=spec,
            contract_file_path=file_path,
            received_at=datetime.now(timezone.utc),
        )

        # Find stipulation
        stipulation = self.linker.find_stipulation_by_path(file_path)

        return contract, stipulation

    def _load_spec_file(self, file_path: str) -> Dict[str, Any]:
        """Load OpenAPI spec from YAML or JSON file."""
        path = Path(file_path)
        with open(path, "r") as f:
            if path.suffix in [".yaml", ".yml"]:
                # Safe: yaml.safe_load on a valid OpenAPI spec always produces a dict
                return cast(Dict[str, Any], yaml.safe_load(f))
            else:
                # Safe: json.load on a valid OpenAPI spec always produces a dict
                return cast(Dict[str, Any], json.load(f))

    def _parse_path(self, file_path: str) -> tuple[str, str]:
        """Extract category and version from file path."""
        parts = Path(file_path).parts
        if len(parts) >= 2:
            version = parts[-2]
            category = parts[-3] if len(parts) >= 3 else parts[-2]
            return category, version
        return "unknown", "v1"
