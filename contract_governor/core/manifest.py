"""
Manifest generation for contract-stipulation linking.

Generates manifests that explicitly link contracts to their stipulations.
"""

import hashlib
from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass
class ContractManifestEntry:
    """Entry for a contract in the manifest."""

    path: str
    sha256: str
    category: str
    version: str
    stipulation: str  # Path to linked stipulation


@dataclass
class StipulationManifestEntry:
    """Entry for a stipulation in the manifest."""

    path: str
    sha256: str
    category: str
    version: str


@dataclass
class ContractStipulationLink:
    """Explicit link between contract and stipulation."""

    contract: str
    stipulation: str


@dataclass
class Manifest:
    """Manifest linking contracts to stipulations."""

    contracts: List[ContractManifestEntry] = field(default_factory=list)
    stipulations: List[StipulationManifestEntry] = field(default_factory=list)
    links: List[ContractStipulationLink] = field(default_factory=list)

    def add_contract(self, path: str, category: str, version: str, stipulation_path: str, content: bytes) -> None:
        """Add contract entry to manifest."""
        sha256 = hashlib.sha256(content).hexdigest()

        self.contracts.append(
            ContractManifestEntry(
                path=path, sha256=sha256, category=category, version=version, stipulation=stipulation_path
            )
        )

        self.links.append(ContractStipulationLink(contract=path, stipulation=stipulation_path))

    def add_stipulation(self, path: str, category: str, version: str, content: bytes) -> None:
        """Add stipulation entry to manifest."""
        sha256 = hashlib.sha256(content).hexdigest()

        self.stipulations.append(StipulationManifestEntry(path=path, sha256=sha256, category=category, version=version))

    def to_dict(self) -> Dict[str, Any]:
        """Convert manifest to dictionary."""
        return {
            "contracts": [
                {
                    "path": c.path,
                    "sha256": c.sha256,
                    "category": c.category,
                    "version": c.version,
                    "stipulation": c.stipulation,
                }
                for c in self.contracts
            ],
            "stipulations": [
                {"path": s.path, "sha256": s.sha256, "category": s.category, "version": s.version}
                for s in self.stipulations
            ],
            "links": [{"contract": link.contract, "stipulation": link.stipulation} for link in self.links],
        }
