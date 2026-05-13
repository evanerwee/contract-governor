"""
Focused interfaces for transformation concerns implementing Interface Segregation Principle.

These interfaces separate transformation concerns so that clients only depend on
the specific transformation capabilities they need, not on unused methods.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List

from ..core.models import StipulationConfig, TransformContext


class URLTransformer(ABC):
    """
    Interface focused solely on URL transformation.

    Clients that only need URL rewriting don't depend on metadata
    or security transformation methods.
    """

    @abstractmethod
    def rewrite_server_urls(self, contract: Dict[str, Any], context: TransformContext) -> Dict[str, Any]:
        """Rewrite server URLs to proxy-safe URLs."""
        pass

    @abstractmethod
    def build_proxy_url(self, stipulation: StipulationConfig, context: TransformContext) -> str:
        """Build proxy URL from stipulation format and context."""
        pass

    @abstractmethod
    def validate_url_template(self, template: str, context: TransformContext) -> bool:
        """Validate that URL template can be resolved with given context."""
        pass


class MetadataInjector(ABC):
    """
    Interface focused solely on metadata injection.

    Clients that only need metadata injection don't depend on URL
    or security transformation methods.
    """

    @abstractmethod
    def inject_audit_metadata(self, contract: Dict[str, Any], stipulation: StipulationConfig, context: TransformContext) -> Dict[str, Any]:
        """Inject audit and governance metadata into contract."""
        pass

    @abstractmethod
    def inject_custom_metadata(self, contract: Dict[str, Any], metadata: Dict[str, Any], namespace: str) -> Dict[str, Any]:
        """Inject custom metadata under specified namespace."""
        pass

    @abstractmethod
    def generate_stipulation_hash(self, stipulation: StipulationConfig) -> str:
        """Generate hash of stipulation for non-repudiation."""
        pass


class SecurityTransformer(ABC):
    """
    Interface focused solely on security transformations.

    Clients that only need security transformations don't depend on URL
    or metadata transformation methods.
    """

    @abstractmethod
    def strip_forbidden_methods(self, contract: Dict[str, Any], forbidden_methods: List[str]) -> Dict[str, Any]:
        """Remove forbidden HTTP methods from contract."""
        pass

    @abstractmethod
    def sanitize_internal_references(self, contract: Dict[str, Any]) -> Dict[str, Any]:
        """Remove or sanitize internal system references."""
        pass

    @abstractmethod
    def apply_security_policies(self, contract: Dict[str, Any], stipulation: StipulationConfig) -> Dict[str, Any]:
        """Apply security policies to contract."""
        pass
