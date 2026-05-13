"""
Shared field validation utilities for stipulation configuration sources.

This module provides utility functions for validating and filtering fields
in stipulation configurations, ensuring consistent behavior across all
config sources (LocalFile, S3, DynamoDB).

Requirements: 6.1, 6.2, 6.3
"""

from dataclasses import dataclass, field, fields
from typing import Any, Dict, List, Optional, Set, Tuple

from ..core.models import StipulationConfig


def get_valid_stipulation_fields() -> Set[str]:
    """
    Get the set of valid field names for StipulationConfig.

    Uses dataclass introspection to automatically reflect any changes
    to the StipulationConfig model.

    Returns:
        Set of valid field names defined in StipulationConfig

    Requirements: 6.3
    """
    return {f.name for f in fields(StipulationConfig)}


def filter_unknown_fields(data: Dict[str, Any]) -> Tuple[Dict[str, Any], List[str]]:
    """
    Filter unknown fields from stipulation data.

    Separates valid fields from unknown fields, allowing the caller
    to handle unknown fields appropriately (e.g., logging warnings).

    Args:
        data: Dictionary containing stipulation configuration data

    Returns:
        Tuple of (filtered_data, list_of_unknown_fields)
        - filtered_data: Dictionary containing only valid StipulationConfig fields
        - list_of_unknown_fields: List of field names that were filtered out

    Requirements: 6.1
    """
    valid_fields = get_valid_stipulation_fields()
    unknown_fields = [k for k in data if k not in valid_fields]
    filtered_data = {k: v for k, v in data.items() if k in valid_fields}
    return filtered_data, unknown_fields


def format_unknown_fields_warning(
    source_path: str,
    unknown_fields: List[str],
    valid_fields: Set[str]
) -> str:
    """
    Format a warning message for unknown fields.

    Creates a consistent, informative warning message that includes
    the source path, unknown fields, and valid fields for reference.

    Args:
        source_path: Path to the source (file path, S3 key, or DynamoDB key)
        unknown_fields: List of field names that were not recognized
        valid_fields: Set of valid field names for reference

    Returns:
        Formatted warning message string

    Requirements: 1.1, 1.2, 6.2
    """
    return (
        f"Stipulation at '{source_path}' contains unsupported fields: {unknown_fields}. "
        f"These fields were ignored. Valid fields are: {sorted(valid_fields)}"
    )


@dataclass
class ParseResult:
    """
    Result of attempting to parse a stipulation configuration.

    Tracks detailed information about the parsing outcome, including
    whether the source exists, what fields were filtered, and any
    error messages.

    Requirements: 2.1, 2.2, 2.3
    """

    success: bool
    config: Optional[StipulationConfig] = None
    source_path: str = ""  # File path, S3 key, or DynamoDB key
    source_exists: bool = False
    unknown_fields: List[str] = field(default_factory=list)
    valid_fields: Set[str] = field(default_factory=set)
    error_message: Optional[str] = None

    @property
    def had_unknown_fields(self) -> bool:
        """Check if unknown fields were filtered during parsing."""
        return len(self.unknown_fields) > 0

    def __post_init__(self):
        """Initialize valid_fields if not provided."""
        if not self.valid_fields:
            self.valid_fields = get_valid_stipulation_fields()
