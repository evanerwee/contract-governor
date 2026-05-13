"""
OpenAPI contract validation using openapi-core library.

This module provides robust validation of OpenAPI specifications before they are
ingested into the contract-governor system. It catches malformed contracts early
to prevent cascading failures during contract exposure and proxy operations.
"""

import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


@dataclass
class ValidationError:
    """Represents a validation error in an OpenAPI spec."""
    field: str
    message: str
    severity: str  # 'error' or 'warning'
    path: Optional[str] = None


@dataclass
class ValidationReport:
    """Comprehensive validation report for an OpenAPI spec."""
    is_valid: bool
    errors: List[ValidationError]
    warnings: List[ValidationError]
    spec_version: Optional[str] = None
    spec_title: Optional[str] = None

    def has_errors(self) -> bool:
        """Check if there are any errors."""
        return len(self.errors) > 0

    def has_warnings(self) -> bool:
        """Check if there are any warnings."""
        return len(self.warnings) > 0

    def get_summary(self) -> str:
        """Get a human-readable summary of the validation."""
        if self.is_valid:
            if self.has_warnings():
                return f"Valid with {len(self.warnings)} warning(s)"
            return "Valid"
        return f"Invalid: {len(self.errors)} error(s), {len(self.warnings)} warning(s)"


class OpenAPIValidator:
    """
    Validates OpenAPI specifications using openapi-core library.

    This validator performs comprehensive validation including:
    - Schema structure validation
    - Required fields validation
    - Type checking
    - Reference resolution
    - Path and operation validation
    """

    def __init__(self, strict_mode: bool = False):
        """
        Initialize the validator.

        Args:
            strict_mode: If True, warnings are treated as errors
        """
        self.strict_mode = strict_mode
        self._openapi_core_available = self._check_openapi_core()

    def _check_openapi_core(self) -> bool:
        """Check if openapi-core library is available."""
        try:
            import openapi_core
            return True
        except ImportError:
            logger.warning(
                "openapi-core library not available. "
                "Install with: pip install openapi-core"
            )
            return False

    def validate(self, spec: Dict[str, Any], file_path: str = "unknown") -> ValidationReport:
        """
        Validate an OpenAPI specification.

        Args:
            spec: The OpenAPI specification dictionary
            file_path: Path to the file (for logging)

        Returns:
            ValidationReport with detailed validation results
        """
        errors = []
        warnings = []

        # Extract basic info
        spec_version = spec.get('openapi') or spec.get('swagger')
        spec_title = spec.get('info', {}).get('title', 'Unknown')

        # Basic structure validation (always performed)
        basic_errors, basic_warnings = self._validate_basic_structure(spec, file_path)
        errors.extend(basic_errors)
        warnings.extend(basic_warnings)

        # If openapi-core is available, perform deep validation
        if self._openapi_core_available and not errors:
            deep_errors, deep_warnings = self._validate_with_openapi_core(spec, file_path)
            errors.extend(deep_errors)
            warnings.extend(deep_warnings)

        # In strict mode, warnings become errors
        if self.strict_mode and warnings:
            errors.extend(warnings)
            warnings = []

        is_valid = len(errors) == 0

        return ValidationReport(
            is_valid=is_valid,
            errors=errors,
            warnings=warnings,
            spec_version=spec_version,
            spec_title=spec_title
        )

    def _validate_basic_structure(
        self,
        spec: Dict[str, Any],
        file_path: str
    ) -> Tuple[List[ValidationError], List[ValidationError]]:
        """
        Perform basic structure validation.

        This catches the most common issues without requiring external libraries.
        """
        errors: list[ValidationError] = []
        warnings: list[ValidationError] = []

        # Must have openapi or swagger field
        if 'openapi' not in spec and 'swagger' not in spec:
            errors.append(ValidationError(
                field='openapi/swagger',
                message='Missing required field: must have either "openapi" or "swagger"',
                severity='error',
                path=file_path
            ))
            return errors, warnings  # Can't continue without version

        # Must have info section
        if 'info' not in spec:
            errors.append(ValidationError(
                field='info',
                message='Missing required "info" section',
                severity='error',
                path=file_path
            ))
        else:
            # Validate info section
            info = spec['info']
            if 'title' not in info:
                errors.append(ValidationError(
                    field='info.title',
                    message='Missing required field "info.title"',
                    severity='error',
                    path=file_path
                ))
            if 'version' not in info:
                errors.append(ValidationError(
                    field='info.version',
                    message='Missing required field "info.version"',
                    severity='error',
                    path=file_path
                ))

        # Must have paths section
        if 'paths' not in spec:
            errors.append(ValidationError(
                field='paths',
                message='Missing required "paths" section',
                severity='error',
                path=file_path
            ))
        else:
            # Validate paths section
            paths = spec['paths']
            if not isinstance(paths, dict):
                errors.append(ValidationError(
                    field='paths',
                    message='"paths" must be a dictionary',
                    severity='error',
                    path=file_path
                ))
            elif len(paths) == 0:
                warnings.append(ValidationError(
                    field='paths',
                    message='"paths" section is empty - no endpoints defined',
                    severity='warning',
                    path=file_path
                ))
            else:
                # Validate each path
                for path_name, path_item in paths.items():
                    if not path_name.startswith('/'):
                        errors.append(ValidationError(
                            field=f'paths.{path_name}',
                            message=f'Path must start with "/": {path_name}',
                            severity='error',
                            path=file_path
                        ))

                    if not isinstance(path_item, dict):
                        errors.append(ValidationError(
                            field=f'paths.{path_name}',
                            message='Path item must be a dictionary',
                            severity='error',
                            path=file_path
                        ))
                        continue

                    # Check for at least one HTTP method
                    http_methods = {'get', 'post', 'put', 'patch', 'delete', 'options', 'head', 'trace'}
                    has_method = any(method in path_item for method in http_methods)
                    if not has_method and '$ref' not in path_item:
                        warnings.append(ValidationError(
                            field=f'paths.{path_name}',
                            message=f'Path has no HTTP methods defined: {path_name}',
                            severity='warning',
                            path=file_path
                        ))

        # Validate servers (if present)
        if 'servers' in spec:
            servers = spec['servers']
            if not isinstance(servers, list):
                errors.append(ValidationError(
                    field='servers',
                    message='"servers" must be an array',
                    severity='error',
                    path=file_path
                ))
            elif len(servers) == 0:
                warnings.append(ValidationError(
                    field='servers',
                    message='"servers" array is empty',
                    severity='warning',
                    path=file_path
                ))
            else:
                for idx, server in enumerate(servers):
                    if not isinstance(server, dict):
                        errors.append(ValidationError(
                            field=f'servers[{idx}]',
                            message='Server must be a dictionary',
                            severity='error',
                            path=file_path
                        ))
                    elif 'url' not in server:
                        errors.append(ValidationError(
                            field=f'servers[{idx}]',
                            message='Server must have a "url" field',
                            severity='error',
                            path=file_path
                        ))

        return errors, warnings

    def _validate_with_openapi_core(
        self,
        spec: Dict[str, Any],
        file_path: str
    ) -> Tuple[List[ValidationError], List[ValidationError]]:
        """
        Perform deep validation using openapi-core library.

        This catches schema issues, reference problems, and other complex validation.
        """
        errors = []
        warnings = []

        try:
            from openapi_core import Spec
            from openapi_core.validation.exceptions import OpenAPIError

            # Create Spec object - this validates the spec structure
            try:
                Spec.from_dict(spec)
                logger.debug(f"✅ OpenAPI spec validated successfully: {file_path}")
            except OpenAPIError as e:
                errors.append(ValidationError(
                    field='spec',
                    message=f'OpenAPI validation error: {str(e)}',
                    severity='error',
                    path=file_path
                ))
            except Exception as e:
                errors.append(ValidationError(
                    field='spec',
                    message=f'Unexpected validation error: {str(e)}',
                    severity='error',
                    path=file_path
                ))

        except ImportError:
            # This shouldn't happen since we checked earlier, but just in case
            warnings.append(ValidationError(
                field='validation',
                message='openapi-core not available, skipping deep validation',
                severity='warning',
                path=file_path
            ))

        return errors, warnings

    def validate_and_log(self, spec: Dict[str, Any], file_path: str) -> bool:
        """
        Validate a spec and log the results.

        Args:
            spec: The OpenAPI specification dictionary
            file_path: Path to the file (for logging)

        Returns:
            True if valid, False otherwise
        """
        report = self.validate(spec, file_path)

        if report.is_valid:
            logger.info(f"✅ Valid OpenAPI spec: {file_path} ({report.spec_title})")
            if report.has_warnings():
                for warning in report.warnings:
                    logger.warning(f"  ⚠️  {warning.field}: {warning.message}")
        else:
            logger.error(f"❌ Invalid OpenAPI spec: {file_path} ({report.spec_title})")
            for error in report.errors:
                logger.error(f"  ❌ {error.field}: {error.message}")
            if report.has_warnings():
                for warning in report.warnings:
                    logger.warning(f"  ⚠️  {warning.field}: {warning.message}")

        return report.is_valid


# Global validator instance
_global_validator: Optional[OpenAPIValidator] = None


def get_global_validator(strict_mode: bool = False) -> OpenAPIValidator:
    """Get or create the global validator instance."""
    global _global_validator
    if _global_validator is None:
        _global_validator = OpenAPIValidator(strict_mode=strict_mode)
    return _global_validator


def validate_openapi_spec(spec: Dict[str, Any], file_path: str = "unknown") -> bool:
    """
    Convenience function to validate an OpenAPI spec.

    Args:
        spec: The OpenAPI specification dictionary
        file_path: Path to the file (for logging)

    Returns:
        True if valid, False otherwise
    """
    validator = get_global_validator()
    return validator.validate_and_log(spec, file_path)
