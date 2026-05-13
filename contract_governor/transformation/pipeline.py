"""
Transformation pipeline implementation for contract stipulation compliance.

This module implements the Chain of Responsibility pattern to transform
OpenAPI contracts according to stipulation policies. Each transformer in the
chain focuses on a specific aspect of contract transformation.
"""

import copy
import time
from datetime import datetime, timezone
from typing import Any, Dict, List

from ..core.models import StipulationConfig, TransformContext
from ..core.monitoring import OperationType, get_global_performance_monitor
from .transformers import AuditMetadataInjector, BaseTransformer, MethodStripper, URLRewriter


class TransformationPipeline:
    """
    Orchestrates contract transformation through a chain of transformers.

    Follows the Chain of Responsibility pattern where each transformer
    can process the contract and pass it to the next transformer in the chain.
    """

    def __init__(self, stipulation: StipulationConfig):
        """
        Initialize the transformation pipeline with a stipulation configuration.

        Args:
            stipulation: The stipulation configuration to transform according to
        """
        self.stipulation = stipulation
        self.transformers: List[BaseTransformer] = []
        self._setup_default_transformers()

    def _setup_default_transformers(self) -> None:
        """Set up the default chain of transformers."""
        self.transformers = [
            URLRewriter(),           # Rewrite internal URLs to proxy URLs
            MethodStripper(),        # Remove forbidden HTTP methods
            AuditMetadataInjector(), # Inject governance and audit metadata
        ]

    def add_transformer(self, transformer: BaseTransformer) -> None:
        """
        Add a custom transformer to the pipeline.

        Args:
            transformer: The transformer to add to the chain
        """
        if not isinstance(transformer, BaseTransformer):
            raise TypeError("Transformer must inherit from BaseTransformer")

        self.transformers.append(transformer)

    def remove_transformer(self, transformer_class: type) -> bool:
        """
        Remove a transformer from the pipeline by class type.

        Args:
            transformer_class: The class of transformer to remove

        Returns:
            True if transformer was removed, False if not found
        """
        for i, transformer in enumerate(self.transformers):
            if isinstance(transformer, transformer_class):
                del self.transformers[i]
                return True
        return False

    def transform(self, contract: Dict[str, Any], context: TransformContext) -> Dict[str, Any]:
        """
        Transform a contract according to the stipulation using all transformers in the chain.

        Args:
            contract: The OpenAPI contract specification to transform
            context: The transformation context with parameters and metadata

        Returns:
            Transformed OpenAPI contract specification
        """
        start_time = time.time()

        # Get performance monitor for metrics
        perf_monitor = get_global_performance_monitor()
        if perf_monitor is None:
            raise RuntimeError("Performance monitor is not initialized")

        # Monitor transformation operation
        with perf_monitor.monitor_operation(
            operation_type=OperationType.TRANSFORMATION,
            contract_category=context.category,
            api_major_version=context.api_major_version,
            stipulation_id=self.stipulation.stipulation_id
        ):
            # Create a deep copy to avoid modifying the original contract
            transformed_contract = copy.deepcopy(contract)

            # Validate inputs
            if not isinstance(contract, dict):
                raise ValueError("Contract must be a dictionary")

            if not isinstance(context, TransformContext):
                raise ValueError("Context must be a TransformContext instance")

            # Run each transformer in the chain
            transformers_applied = 0
            for transformer in self.transformers:
                try:
                    transformed_contract = transformer.transform(
                        transformed_contract,
                        context,
                        self.stipulation
                    )
                    transformers_applied += 1

                    # Validate that transformer returned a valid contract
                    if not isinstance(transformed_contract, dict):
                        raise ValueError(f"Transformer {transformer.__class__.__name__} returned invalid contract type")

                except Exception as e:
                    # Handle transformer exceptions
                    raise RuntimeError(
                        f"Transformer {transformer.__class__.__name__} failed: {str(e)}"
                    ) from e

            # Record transformation metadata
            transformation_duration_ms = int((time.time() - start_time) * 1000)

            # Record detailed transformation metrics
            perf_monitor.record_transformation_metrics(
                contract_category=context.category,
                api_major_version=context.api_major_version,
                stipulation_id=self.stipulation.stipulation_id,
                transformation_duration=transformation_duration_ms / 1000.0,
                transformers_applied=transformers_applied,
                success=True
            )

            # Add transformation metadata to the contract if not already present
            if 'x-transformation-metadata' not in transformed_contract:
                transformed_contract['x-transformation-metadata'] = {
                    'stipulation_id': self.stipulation.stipulation_id,
                    'transformation_duration_ms': transformation_duration_ms,
                    'transformers_applied': [t.__class__.__name__ for t in self.transformers],
                    'transformation_timestamp': datetime.now(timezone.utc).isoformat()
                }

            return transformed_contract

    def get_transformer_info(self) -> List[Dict[str, str]]:
        """
        Get information about all transformers in the pipeline.

        Returns:
            List of dictionaries with transformer information
        """
        return [
            {
                "name": transformer.__class__.__name__,
                "description": getattr(transformer, "__doc__", "").strip().split('\n')[0] if transformer.__doc__ else "",
                "module": transformer.__class__.__module__
            }
            for transformer in self.transformers
        ]

    def validate_transformation_capability(self, context: TransformContext) -> List[str]:
        """
        Check if this pipeline can transform contracts for the given context.

        Args:
            context: The transformation context to check compatibility with

        Returns:
            List of capability issues, empty if compatible
        """
        issues = []

        # Check if transformers can handle the context requirements
        if self.stipulation.exposure_policy.value == "tenant-scoped":
            if not context.scope_parameters:
                issues.append("Tenant-scoped transformation requires scope parameters in context")
            elif self.stipulation.requires_scope_parameter:
                required_params = []
                if self.stipulation.proxy_prefix_format and "{tenant_id}" in self.stipulation.proxy_prefix_format:
                    required_params.append("tenant_id")
                if self.stipulation.proxy_prefix_format and "{scope_id}" in self.stipulation.proxy_prefix_format:
                    required_params.append("scope_id")

                missing_params = [p for p in required_params if p not in context.scope_parameters]
                if missing_params:
                    issues.append(f"Missing required scope parameters: {missing_params}")

        # Check gateway base URL compatibility
        if not context.gateway_base_url:
            issues.append("Gateway base URL is required for URL rewriting")

        return issues

    def preview_transformation(self, contract: Dict[str, Any], context: TransformContext) -> Dict[str, Any]:
        """
        Preview what the transformation would do without actually modifying the contract.

        Args:
            contract: The contract to preview transformation for
            context: The transformation context

        Returns:
            Dictionary describing the planned transformations
        """
        preview: Dict[str, Any] = {
            "stipulation_id": self.stipulation.stipulation_id,
            "transformers": [],
            "estimated_changes": {}
        }

        # Get preview from each transformer
        for transformer in self.transformers:
            if hasattr(transformer, 'preview_transformation'):
                transformer_preview = transformer.preview_transformation(contract, context, self.stipulation)
                preview["transformers"].append({
                    "name": transformer.__class__.__name__,
                    "preview": transformer_preview
                })

        # Estimate overall changes
        if "servers" in contract:
            preview["estimated_changes"]["servers"] = "Will be rewritten to proxy URLs"

        if "paths" in contract:
            forbidden_methods = [m.lower() for m in self.stipulation.forbid_methods]
            methods_to_remove = []
            for path, path_obj in contract["paths"].items():
                if isinstance(path_obj, dict):
                    for method in path_obj.keys():
                        if method.lower() in forbidden_methods:
                            methods_to_remove.append(f"{method.upper()} {path}")

            if methods_to_remove:
                preview["estimated_changes"]["forbidden_methods"] = f"Will remove: {', '.join(methods_to_remove)}"

        if self.stipulation.inject_metadata:
            preview["estimated_changes"]["metadata"] = f"Will inject audit metadata under {self.stipulation.extension_namespace}"

        return preview
