"""
Validation pipeline implementation for contract stipulation compliance.

This module implements the Chain of Responsibility pattern to validate
OpenAPI contracts against stipulation policies. Each validator in the
chain focuses on a specific aspect of compliance checking.
"""

import time
from datetime import datetime, timezone
from typing import Any, Dict, List

from ..core.models import StipulationConfig, ValidationResult
from ..core.monitoring import OperationType, get_global_performance_monitor
from .validators import (
    BaseValidator,
    ForbiddenMethodsValidator,
    OpenAPIVersionValidator,
    RequiredFieldsValidator,
    TenantScopingValidator,
    VersionAlignmentValidator,
)


class ValidationPipeline:
    """
    Orchestrates contract validation through a chain of validators.

    Follows the Chain of Responsibility pattern where each validator
    can process the contract and pass it to the next validator in the chain.
    """

    def __init__(self, stipulation: StipulationConfig):
        """
        Initialize the validation pipeline with a stipulation configuration.

        Args:
            stipulation: The stipulation configuration to validate against
        """
        self.stipulation = stipulation
        self.validators: List[BaseValidator] = []
        self._setup_default_validators()

    def _setup_default_validators(self) -> None:
        """Set up the default chain of validators."""
        self.validators = [
            OpenAPIVersionValidator(),
            RequiredFieldsValidator(),
            ForbiddenMethodsValidator(),
            TenantScopingValidator(),
            VersionAlignmentValidator()
        ]

    def add_validator(self, validator: BaseValidator) -> None:
        """
        Add a custom validator to the pipeline.

        Args:
            validator: The validator to add to the chain
        """
        if not isinstance(validator, BaseValidator):
            raise TypeError("Validator must inherit from BaseValidator")

        self.validators.append(validator)

    def remove_validator(self, validator_class: type) -> bool:
        """
        Remove a validator from the pipeline by class type.

        Args:
            validator_class: The class of validator to remove

        Returns:
            True if validator was removed, False if not found
        """
        for i, validator in enumerate(self.validators):
            if isinstance(validator, validator_class):
                del self.validators[i]
                return True
        return False

    def validate(self, contract: Dict[str, Any]) -> ValidationResult:
        """
        Validate a contract against the stipulation using all validators in the chain.

        Args:
            contract: The OpenAPI contract specification to validate

        Returns:
            ValidationResult with aggregated errors and warnings from all validators
        """
        start_time = time.time()

        # Get performance monitor for metrics
        perf_monitor = get_global_performance_monitor()
        if perf_monitor is None:
            raise RuntimeError("Performance monitor not initialized")

        # Monitor validation operation
        with perf_monitor.monitor_operation(
            operation_type=OperationType.VALIDATION,
            contract_category=getattr(self.stipulation, 'category', None),
            api_major_version=getattr(self.stipulation, 'api_major_version', None),
            stipulation_id=self.stipulation.stipulation_id
        ):
            # Initialize result
            result = ValidationResult(
                is_valid=True,
                applied_stipulation=self.stipulation.stipulation_id,
                validation_timestamp=datetime.now(timezone.utc),
                contract_category=getattr(self.stipulation, 'category', None),
                validator_version="1.0.0"
            )

            # Validate contract structure first
            if not self._validate_contract_structure(contract, result):
                # If basic structure is invalid, don't proceed with other validators
                result.validation_duration_ms = int((time.time() - start_time) * 1000)
                return result

            # Run each validator in the chain
            for validator in self.validators:
                try:
                    validator_result = validator.validate(contract, self.stipulation)

                    # Aggregate errors and warnings
                    result.errors.extend(validator_result.errors)
                    result.warnings.extend(validator_result.warnings)

                    # If any validator reports invalid, mark overall result as invalid
                    if not validator_result.is_valid:
                        result.is_valid = False

                except Exception as e:
                    # Handle validator exceptions gracefully
                    result.add_error(
                        code="VALIDATOR_EXCEPTION",
                        message=f"Validator {validator.__class__.__name__} failed: {str(e)}",
                        stipulation_id=self.stipulation.stipulation_id,
                        validator_class=validator.__class__.__name__
                    )

            # Final validation state check
            if result.errors:
                result.is_valid = False

            # Record validation duration
            result.validation_duration_ms = int((time.time() - start_time) * 1000)

            # Record detailed validation metrics
            perf_monitor.record_validation_metrics(
                contract_category=getattr(self.stipulation, 'category', 'unknown'),
                api_major_version=getattr(self.stipulation, 'api_major_version', 'unknown'),
                stipulation_id=self.stipulation.stipulation_id,
                validation_duration=result.validation_duration_ms / 1000.0,
                validation_errors=len(result.errors),
                validation_warnings=len(result.warnings),
                success=result.is_valid
            )

            return result

    def _validate_contract_structure(self, contract: Dict[str, Any], result: ValidationResult) -> bool:
        """
        Validate basic OpenAPI contract structure before running specific validators.

        Args:
            contract: The contract to validate
            result: The validation result to update with any errors

        Returns:
            True if structure is valid, False otherwise
        """
        if not isinstance(contract, dict):
            result.add_error(
                code="INVALID_CONTRACT_TYPE",
                message="Contract must be a dictionary/object",
                stipulation_id=self.stipulation.stipulation_id
            )
            return False

        if not contract:
            result.add_error(
                code="EMPTY_CONTRACT",
                message="Contract cannot be empty",
                stipulation_id=self.stipulation.stipulation_id
            )
            return False

        # Check for required top-level OpenAPI fields
        required_top_level = ["openapi", "info"]
        for field in required_top_level:
            if field not in contract:
                result.add_error(
                    code="MISSING_REQUIRED_TOP_LEVEL_FIELD",
                    message=f"Required top-level field '{field}' is missing",
                    field_path=field,
                    stipulation_id=self.stipulation.stipulation_id
                )

        # Validate info section structure
        if "info" in contract:
            info = contract["info"]
            if not isinstance(info, dict):
                result.add_error(
                    code="INVALID_INFO_SECTION",
                    message="The 'info' section must be an object",
                    field_path="info",
                    stipulation_id=self.stipulation.stipulation_id
                )
            else:
                # Check required info fields
                required_info_fields = ["title", "version"]
                for field in required_info_fields:
                    if field not in info:
                        result.add_error(
                            code="MISSING_REQUIRED_INFO_FIELD",
                            message=f"Required info field '{field}' is missing",
                            field_path=f"info.{field}",
                            stipulation_id=self.stipulation.stipulation_id
                        )

        # Return True if no structural errors were found
        return not result.has_errors()

    def get_validator_info(self) -> List[Dict[str, str]]:
        """
        Get information about all validators in the pipeline.

        Returns:
            List of dictionaries with validator information
        """
        return [
            {
                "name": validator.__class__.__name__,
                "description": getattr(validator, "__doc__", "").strip().split('\n')[0] if validator.__doc__ else "",
                "module": validator.__class__.__module__
            }
            for validator in self.validators
        ]

    def validate_stipulation_compatibility(self, other_stipulation: StipulationConfig) -> List[str]:
        """
        Check if this pipeline can validate contracts for another stipulation.

        Args:
            other_stipulation: The stipulation to check compatibility with

        Returns:
            List of compatibility issues, empty if compatible
        """
        issues = []

        # Check if validators can handle the other stipulation's requirements
        if other_stipulation.require_openapi_major != self.stipulation.require_openapi_major:
            issues.append(f"OpenAPI version requirement mismatch: {other_stipulation.require_openapi_major} vs {self.stipulation.require_openapi_major}")

        if other_stipulation.exposure_policy != self.stipulation.exposure_policy:
            issues.append(f"Exposure policy mismatch: {other_stipulation.exposure_policy} vs {self.stipulation.exposure_policy}")

        return issues
