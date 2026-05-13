"""
Abstract interface for contract validator implementations.

This interface implements the Dependency Inversion Principle by allowing
the validation pipeline to work with any validator implementation without
depending on specific validation logic.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict

from ..core.models import StipulationConfig, ValidationResult


class Validator(ABC):
    """
    Abstract interface for validating OpenAPI contracts against stipulation policies.

    This interface allows the validation pipeline to be extended with new
    validators without modifying existing code, following the Open/Closed Principle.
    """

    @abstractmethod
    def validate(self, contract: Dict[str, Any], stipulation: StipulationConfig) -> ValidationResult:
        """
        Validate an OpenAPI contract against a stipulation configuration.

        Args:
            contract: OpenAPI specification as dictionary
            stipulation: Stipulation configuration to validate against

        Returns:
            ValidationResult containing validation outcome and any errors/warnings
        """
        pass

    @abstractmethod
    def get_validator_name(self) -> str:
        """
        Get the name of this validator for logging and error reporting.

        Returns:
            Human-readable name of the validator
        """
        pass

    @abstractmethod
    def get_supported_stipulation_fields(self) -> list[str]:
        """
        Get the list of stipulation fields this validator uses.

        Returns:
            List of StipulationConfig field names this validator depends on
        """
        pass

    @abstractmethod
    def is_applicable(self, stipulation: StipulationConfig) -> bool:
        """
        Check if this validator should be applied for the given stipulation.

        Args:
            stipulation: Stipulation configuration

        Returns:
            True if validator should run, False to skip
        """
        pass
