"""
Focused interfaces for validation concerns implementing Interface Segregation Principle.

These interfaces separate validation concerns so that clients only depend on
the specific validation capabilities they need, not on unused methods.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List

from ..core.models import StipulationConfig, ValidationResult


class ContractStructureValidator(ABC):
    """
    Interface focused solely on OpenAPI contract structure validation.

    Clients that only need structure validation don't depend on policy
    or security validation methods.
    """

    @abstractmethod
    def validate_openapi_version(self, contract: Dict[str, Any]) -> ValidationResult:
        """Validate OpenAPI specification version."""
        pass

    @abstractmethod
    def validate_required_fields(self, contract: Dict[str, Any], required_fields: List[str]) -> ValidationResult:
        """Validate presence of required fields."""
        pass

    @abstractmethod
    def validate_schema_structure(self, contract: Dict[str, Any]) -> ValidationResult:
        """Validate overall schema structure."""
        pass


class PolicyValidator(ABC):
    """
    Interface focused solely on policy compliance validation.

    Clients that only need policy validation don't depend on structure
    or security validation methods.
    """

    @abstractmethod
    def validate_exposure_policy(self, contract: Dict[str, Any], stipulation: StipulationConfig) -> ValidationResult:
        """Validate contract against exposure policy requirements."""
        pass

    @abstractmethod
    def validate_version_alignment(self, contract: Dict[str, Any], stipulation: StipulationConfig) -> ValidationResult:
        """Validate version alignment requirements."""
        pass

    @abstractmethod
    def validate_tenant_scoping(self, contract: Dict[str, Any], stipulation: StipulationConfig) -> ValidationResult:
        """Validate tenant scoping requirements."""
        pass


class SecurityValidator(ABC):
    """
    Interface focused solely on security validation.

    Clients that only need security validation don't depend on structure
    or policy validation methods.
    """

    @abstractmethod
    def validate_forbidden_methods(self, contract: Dict[str, Any], forbidden_methods: List[str]) -> ValidationResult:
        """Validate that contract doesn't contain forbidden HTTP methods."""
        pass

    @abstractmethod
    def validate_url_safety(self, contract: Dict[str, Any]) -> ValidationResult:
        """Validate that URLs are safe for proxy exposure."""
        pass

    @abstractmethod
    def validate_security_schemes(self, contract: Dict[str, Any]) -> ValidationResult:
        """Validate security scheme definitions."""
        pass
