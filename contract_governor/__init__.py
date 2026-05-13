"""
Contract Governor

A policy-driven framework for governing OpenAPI contract validation, transformation,
and exposure in distributed systems.

Copyright (c) 2024-2026 Evan Erwee
Licensed under the MIT License. See LICENSE file in the project root for details.
"""

__version__ = "2.0.1"

from .core.contract_governor import ContractGovernor
from .core.models import (
    ExposedContractRecord,
    RawContractRecord,
    StipulationConfig,
    TransformContext,
    ValidationResult,
    VersionInfo,
)

__all__ = [
    "ContractGovernor",
    "StipulationConfig",
    "RawContractRecord",
    "ExposedContractRecord",
    "ValidationResult",
    "TransformContext",
    "VersionInfo",
]
