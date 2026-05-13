"""
Contract-Stipulation linking logic.

Links contracts to stipulations based on category and API major version.
"""

import re
from pathlib import Path
from typing import Any, Dict, Optional, Protocol

from ..interfaces.configuration_source import ConfigurationSource
from ..interfaces.contract_linker import ContractLinker
from .models import StipulationConfig


class PathParser(Protocol):
    """Strategy for parsing contract paths."""

    def parse(self, path: str) -> tuple[str, str]:
        """Parse path to extract (category, version)."""
        ...


class StandardPathParser:
    """Standard path parser: category/version/openapi.yaml"""

    def parse(self, path: str) -> tuple[str, str]:
        """Parse a file path to extract the contract category and version."""
        parts = Path(path).parts
        if len(parts) >= 2:
            category = parts[-3] if len(parts) >= 3 else parts[-2]
            version = parts[-2]
            if version.startswith("v"):
                return category, version
        return "", ""


class StipulationLinker(ContractLinker):
    """Links contracts to their governing stipulations."""

    def __init__(self, config_source: ConfigurationSource, path_parser: PathParser | None = None):
        """Initialize linker with a configuration source and optional path parser."""
        self.config_source = config_source
        self.path_parser = path_parser or StandardPathParser()

    def find_stipulation_by_path(self, contract_path: str) -> Optional[StipulationConfig]:
        """
        Find stipulation for a contract based on its path.

        Args:
            contract_path: Path like "evidence-query/v1/openapi.yaml"

        Returns:
            StipulationConfig if found, None otherwise
        """
        category, version = self.path_parser.parse(contract_path)
        if not category or not version:
            return None

        return self.config_source.load_stipulation(category, version)

    def find_stipulation_by_spec(self, openapi_spec: Dict[str, Any]) -> Optional[StipulationConfig]:
        """Find stipulation based on OpenAPI spec metadata."""
        info = openapi_spec.get("info", {})
        title = info.get("title", "")
        version = info.get("version", "")

        category = openapi_spec.get("x-category") or self._extract_category(title)
        api_major = self._extract_major_version(version)

        if not category or not api_major:
            return None

        return self.config_source.load_stipulation(category, api_major)

    def _extract_category(self, title: str) -> str:
        """Extract category from API title."""
        # Convert "Evidence Query API" -> "evidence-query"
        category = title.lower().replace(" api", "").replace(" ", "-")
        return category

    def _extract_major_version(self, version: str) -> str:
        """Extract major version from semantic version."""
        # "1.0.0" -> "v1"
        match = re.match(r"^(\d+)\.", version)
        if match:
            return f"v{match.group(1)}"
        return ""
