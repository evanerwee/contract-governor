"""
Abstract interface for contract transformer implementations.

This interface implements the Dependency Inversion Principle by allowing
the transformation pipeline to work with any transformer implementation without
depending on specific transformation logic.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict

from ..core.models import StipulationConfig, TransformContext


class Transformer(ABC):
    """
    Abstract interface for transforming OpenAPI contracts according to stipulation policies.

    This interface allows the transformation pipeline to be extended with new
    transformers without modifying existing code, following the Open/Closed Principle.
    """

    @abstractmethod
    def transform(self, contract: Dict[str, Any], context: TransformContext, stipulation: StipulationConfig) -> Dict[str, Any]:
        """
        Transform an OpenAPI contract according to stipulation requirements.

        Args:
            contract: OpenAPI specification as dictionary
            context: Transformation context with metadata and parameters
            stipulation: Stipulation configuration defining transformation rules

        Returns:
            Transformed OpenAPI specification as dictionary
        """
        pass

    @abstractmethod
    def get_transformer_name(self) -> str:
        """
        Get the name of this transformer for logging and error reporting.

        Returns:
            Human-readable name of the transformer
        """
        pass

    @abstractmethod
    def get_supported_stipulation_fields(self) -> list[str]:
        """
        Get the list of stipulation fields this transformer uses.

        Returns:
            List of StipulationConfig field names this transformer depends on
        """
        pass

    @abstractmethod
    def is_applicable(self, stipulation: StipulationConfig) -> bool:
        """
        Check if this transformer should be applied for the given stipulation.

        Args:
            stipulation: Stipulation configuration

        Returns:
            True if transformer should run, False to skip
        """
        pass

    @abstractmethod
    def get_execution_order(self) -> int:
        """
        Get the execution order priority for this transformer.

        Transformers are executed in ascending order of priority.
        Lower numbers execute first.

        Returns:
            Integer priority (0-100, where 0 is highest priority)
        """
        pass
