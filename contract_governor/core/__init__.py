"""
Core module containing the main business logic and orchestration components.

This module implements the Single Responsibility Principle by separating:
- Contract governance and orchestration (ContractGovernor)
- Stipulation policy management (ContractStipulations)
- Data models and value objects
- Contract registry operations
"""

from .contract_governor import ContractGovernor, ContractNotFoundError, StipulationViolationError
from .manifest import ContractManifestEntry, ContractStipulationLink, Manifest, StipulationManifestEntry
from .models import (
    AuditMetadata,
    ExposedContractRecord,
    ExposurePolicy,
    RawContractRecord,
    StipulationConfig,
    StipulationRegistry,
    TransformContext,
    ValidationError,
    ValidationResult,
    ValidationWarning,
    VersionInfo,
)
from .registry import InMemoryContractRegistry
from .stipulation_linker import StandardPathParser, StipulationLinker

__all__ = [
    "ContractGovernor",
    "ContractNotFoundError",
    "StipulationViolationError",
    "InMemoryContractRegistry",
    "StipulationLinker",
    "StandardPathParser",
    "Manifest",
    "ContractManifestEntry",
    "StipulationManifestEntry",
    "ContractStipulationLink",
    "StipulationConfig",
    "StipulationRegistry",
    "ExposurePolicy",
    "RawContractRecord",
    "ExposedContractRecord",
    "ValidationResult",
    "ValidationError",
    "ValidationWarning",
    "TransformContext",
    "VersionInfo",
    "AuditMetadata",
]
