"""
Abstract interface for catalog server implementations.

This interface implements the Dependency Inversion Principle by allowing
high-level modules to depend on this abstraction rather than concrete
framework implementations (FastAPI, Flask, Django, etc.).
"""

from abc import ABC, abstractmethod
from typing import Callable, List, Optional

from ..core.models import ExposedContractRecord


class CatalogServer(ABC):
    """
    Abstract interface for serving API catalogs across different web frameworks.

    This interface ensures framework independence by defining the contract
    that all catalog server implementations must follow, regardless of the
    underlying web framework (FastAPI, Flask, Django, etc.).
    """

    @abstractmethod
    def register_catalog_endpoint(self, path: str, handler: Optional[Callable] = None) -> None:
        """
        Register an endpoint for serving the API catalog.

        Args:
            path: URL path for the catalog endpoint
            handler: Optional custom handler function
        """
        pass

    @abstractmethod
    def register_contract_endpoint(self, path: str, handler: Optional[Callable] = None) -> None:
        """
        Register an endpoint for serving individual contracts.

        Args:
            path: URL path pattern for contract endpoints (may include path parameters)
            handler: Optional custom handler function
        """
        pass

    @abstractmethod
    def serve_openapi_spec(self, spec: dict, path: str) -> None:
        """
        Serve an OpenAPI specification at the given path.

        Args:
            spec: OpenAPI specification as dictionary
            path: URL path where the spec should be served
        """
        pass

    @abstractmethod
    def register_health_endpoints(self) -> None:
        """
        Register health check endpoints for container orchestration.

        Should register both liveness (/health) and readiness (/ready) probes
        suitable for Kubernetes deployments.
        """
        pass

    @abstractmethod
    def get_exposed_contracts(self, filters: Optional[dict] = None) -> List[ExposedContractRecord]:
        """
        Retrieve exposed contracts with optional filtering.

        Args:
            filters: Optional dictionary of filter criteria

        Returns:
            List of exposed contract records
        """
        pass
