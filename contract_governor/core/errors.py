"""
Comprehensive error handling system for Contract Stipulations.

This module provides a structured hierarchy of exceptions and error handling
utilities that support detailed error reporting, HTTP status mapping, and
monitoring integration.
"""

import traceback
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional


class ErrorSeverity(Enum):
    """Error severity levels for classification and monitoring."""

    CRITICAL = "critical"
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


class ErrorCategory(Enum):
    """Error categories for monitoring and alerting."""

    VALIDATION = "validation"
    TRANSFORMATION = "transformation"
    CONFIGURATION = "configuration"
    REGISTRY = "registry"
    NETWORK = "network"
    AUTHENTICATION = "authentication"
    AUTHORIZATION = "authorization"
    SYSTEM = "system"


@dataclass
class ErrorContext:
    """
    Rich context information for errors to support debugging and monitoring.
    """

    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    request_id: Optional[str] = None
    user_id: Optional[str] = None
    service_name: Optional[str] = None
    contract_category: Optional[str] = None
    api_major_version: Optional[str] = None
    stipulation_id: Optional[str] = None
    operation: Optional[str] = None
    additional_data: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert context to dictionary for logging and monitoring."""
        return {
            "timestamp": self.timestamp.isoformat(),
            "request_id": self.request_id,
            "user_id": self.user_id,
            "service_name": self.service_name,
            "contract_category": self.contract_category,
            "api_major_version": self.api_major_version,
            "stipulation_id": self.stipulation_id,
            "operation": self.operation,
            "additional_data": self.additional_data,
        }


class StipulationError(Exception):
    """
    Base exception class for all Contract Stipulations errors.

    Provides structured error information with context for monitoring,
    logging, and HTTP response generation.
    """

    def __init__(
        self,
        message: str,
        error_code: str,
        category: ErrorCategory = ErrorCategory.SYSTEM,
        severity: ErrorSeverity = ErrorSeverity.ERROR,
        context: Optional[ErrorContext] = None,
        cause: Optional[Exception] = None,
        details: Optional[Dict[str, Any]] = None,
    ):
        """Initialize stipulation error with message, code, category, severity, and optional context."""
        super().__init__(message)
        self.message = message
        self.error_code = error_code
        self.category = category
        self.severity = severity
        self.context = context or ErrorContext()
        self.cause = cause
        self.details = details or {}
        self.traceback_info = traceback.format_exc() if cause else None

    def to_dict(self) -> Dict[str, Any]:
        """Convert error to dictionary for API responses and logging."""
        return {
            "error_code": self.error_code,
            "message": self.message,
            "category": self.category.value,
            "severity": self.severity.value,
            "context": self.context.to_dict(),
            "details": self.details,
            "cause": str(self.cause) if self.cause else None,
            "traceback": self.traceback_info,
        }

    def get_http_status_code(self) -> int:
        """Get appropriate HTTP status code for this error."""
        # Default mapping - subclasses can override
        if self.severity == ErrorSeverity.CRITICAL:
            return 500
        elif self.category == ErrorCategory.VALIDATION:
            return 400
        elif self.category == ErrorCategory.AUTHENTICATION:
            return 401
        elif self.category == ErrorCategory.AUTHORIZATION:
            return 403
        elif self.category == ErrorCategory.REGISTRY and "not found" in self.message.lower():
            return 404
        else:
            return 500


class ValidationError(StipulationError):
    """
    Raised when contract validation fails against stipulation requirements.
    """

    def __init__(
        self,
        message: str,
        error_code: str,
        field_path: Optional[str] = None,
        stipulation_id: Optional[str] = None,
        validation_errors: Optional[List[Dict[str, Any]]] = None,
        context: Optional[ErrorContext] = None,
    ):
        """Initialize validation error with field path, stipulation ID, and validation details."""
        super().__init__(
            message=message,
            error_code=error_code,
            category=ErrorCategory.VALIDATION,
            severity=ErrorSeverity.ERROR,
            context=context,
        )
        self.field_path = field_path
        self.stipulation_id = stipulation_id
        self.validation_errors = validation_errors or []

        # Add validation-specific details
        self.details.update(
            {"field_path": field_path, "stipulation_id": stipulation_id, "validation_errors": self.validation_errors}
        )

    def get_http_status_code(self) -> int:
        """Validation errors are always 400 Bad Request."""
        return 400


class TransformationError(StipulationError):
    """
    Raised when contract transformation fails during processing.
    """

    def __init__(
        self,
        message: str,
        error_code: str,
        transformation_stage: Optional[str] = None,
        original_contract: Optional[Dict[str, Any]] = None,
        context: Optional[ErrorContext] = None,
        cause: Optional[Exception] = None,
    ):
        """Initialize transformation error with stage and original contract details."""
        super().__init__(
            message=message,
            error_code=error_code,
            category=ErrorCategory.TRANSFORMATION,
            severity=ErrorSeverity.ERROR,
            context=context,
            cause=cause,
        )
        self.transformation_stage = transformation_stage
        self.original_contract = original_contract

        # Add transformation-specific details
        self.details.update(
            {"transformation_stage": transformation_stage, "has_original_contract": original_contract is not None}
        )

    def get_http_status_code(self) -> int:
        """Transformation errors are typically 422 Unprocessable Entity."""
        return 422


class ConfigurationError(StipulationError):
    """
    Raised when configuration is invalid or missing.
    """

    def __init__(
        self,
        message: str,
        error_code: str,
        config_source: Optional[str] = None,
        config_key: Optional[str] = None,
        context: Optional[ErrorContext] = None,
        cause: Optional[Exception] = None,
    ):
        """Initialize configuration error with source and key details."""
        super().__init__(
            message=message,
            error_code=error_code,
            category=ErrorCategory.CONFIGURATION,
            severity=ErrorSeverity.ERROR,
            context=context,
            cause=cause,
        )
        self.config_source = config_source
        self.config_key = config_key

        # Add configuration-specific details
        self.details.update({"config_source": config_source, "config_key": config_key})

    def get_http_status_code(self) -> int:
        """Configuration errors are typically 500 Internal Server Error."""
        return 500


class RegistryError(StipulationError):
    """
    Raised when contract registry operations fail.
    """

    def __init__(
        self,
        message: str,
        error_code: str,
        operation: Optional[str] = None,
        contract_key: Optional[str] = None,
        context: Optional[ErrorContext] = None,
        cause: Optional[Exception] = None,
    ):
        """Initialize registry error with operation type and contract key."""
        super().__init__(
            message=message,
            error_code=error_code,
            category=ErrorCategory.REGISTRY,
            severity=ErrorSeverity.ERROR,
            context=context,
            cause=cause,
        )
        self.operation = operation
        self.contract_key = contract_key

        # Add registry-specific details
        self.details.update({"operation": operation, "contract_key": contract_key})

    def get_http_status_code(self) -> int:
        """Registry errors map to different HTTP codes based on operation."""
        if self.operation == "get" and "not found" in self.message.lower():
            return 404
        elif self.operation in ["store", "update"]:
            return 422
        else:
            return 500


class ContractNotFoundError(RegistryError):
    """
    Raised when a requested contract is not found in the registry.
    """

    def __init__(
        self,
        category: str,
        api_major_version: str,
        contract_type: str = "exposed",
        context: Optional[ErrorContext] = None,
    ):
        """Initialize contract-not-found error with category, version, and contract type."""
        message = f"{contract_type.title()} contract not found: {category}:{api_major_version}"
        super().__init__(
            message=message,
            error_code="CONTRACT_NOT_FOUND",
            operation="get",
            contract_key=f"{category}:{api_major_version}",
            context=context,
        )
        self.category_name = category
        self.api_major_version = api_major_version
        self.contract_type = contract_type

    def get_http_status_code(self) -> int:
        """Contract not found is always 404."""
        return 404


class StipulationViolationError(ValidationError):
    """
    Raised when a contract violates stipulation requirements.
    """

    def __init__(self, validation_result, context: Optional[ErrorContext] = None):  # ValidationResult from models
        """Initialize stipulation violation error from a validation result."""
        # Extract error messages from validation result
        error_messages = [error.message for error in validation_result.errors]
        message = f"Contract violates stipulation: {'; '.join(error_messages)}"

        # Convert validation errors to dict format
        validation_errors = [error.to_dict() for error in validation_result.errors]

        super().__init__(
            message=message,
            error_code="STIPULATION_VIOLATION",
            stipulation_id=validation_result.applied_stipulation,
            validation_errors=validation_errors,
            context=context,
        )
        self.validation_result = validation_result


class StipulationNotFoundError(StipulationError):
    """
    Raised when no stipulation file exists for a category:api_major key.

    Requirements: 3.3
    """

    def __init__(self, category: str, api_major_version: str, context: Optional[ErrorContext] = None):
        """Initialize stipulation-not-found error with category and API version."""
        message = (
            f"No stipulation found for {category}:{api_major_version}. "
            f"No stipulation file exists for this category and version."
        )
        super().__init__(
            message=message,
            error_code="STIPULATION_NOT_FOUND",
            category=ErrorCategory.CONFIGURATION,
            severity=ErrorSeverity.ERROR,
            context=context,
        )
        self.category_name = category
        self.api_major_version = api_major_version

    def get_http_status_code(self) -> int:
        """Stipulation not found is 404."""
        return 404


class StipulationParseError(StipulationError):
    """
    Raised when a stipulation file exists but failed to parse.

    Requirements: 3.2, 3.4
    """

    def __init__(
        self,
        category: str,
        api_major_version: str,
        source_path: str,
        parse_error: Optional[str] = None,
        unknown_fields: Optional[List[str]] = None,
        context: Optional[ErrorContext] = None,
        cause: Optional[Exception] = None,
    ):
        """Initialize stipulation parse error with source path and parse failure details."""
        if parse_error:
            message = (
                f"Stipulation file exists for {category}:{api_major_version} at '{source_path}' "
                f"but failed to parse: {parse_error}. "
                f"Check logs for details about unsupported fields."
            )
        elif unknown_fields:
            message = (
                f"Stipulation file for {category}:{api_major_version} at '{source_path}' "
                f"contained unknown fields that were filtered: {unknown_fields}. "
                f"The stipulation may have failed validation after filtering."
            )
        else:
            message = (
                f"Stipulation file exists for {category}:{api_major_version} at '{source_path}' "
                f"but failed to load. Check logs for details."
            )

        super().__init__(
            message=message,
            error_code="STIPULATION_PARSE_ERROR",
            category=ErrorCategory.CONFIGURATION,
            severity=ErrorSeverity.ERROR,
            context=context,
            cause=cause,
        )
        self.category_name = category
        self.api_major_version = api_major_version
        self.source_path = source_path
        self.parse_error = parse_error
        self.unknown_fields = unknown_fields or []

        # Add details for debugging
        self.details.update(
            {"source_path": source_path, "parse_error": parse_error, "unknown_fields": self.unknown_fields}
        )

    def get_http_status_code(self) -> int:
        """Parse errors are 422 Unprocessable Entity."""
        return 422


class AuthenticationError(StipulationError):
    """
    Raised when authentication fails.
    """

    def __init__(
        self,
        message: str = "Authentication failed",
        error_code: str = "AUTHENTICATION_FAILED",
        context: Optional[ErrorContext] = None,
    ):
        """Initialize authentication error with message and error code."""
        super().__init__(
            message=message,
            error_code=error_code,
            category=ErrorCategory.AUTHENTICATION,
            severity=ErrorSeverity.ERROR,
            context=context,
        )

    def get_http_status_code(self) -> int:
        """Authentication errors are always 401."""
        return 401


class AuthorizationError(StipulationError):
    """
    Raised when authorization fails.
    """

    def __init__(
        self,
        message: str = "Access denied",
        error_code: str = "ACCESS_DENIED",
        required_permission: Optional[str] = None,
        context: Optional[ErrorContext] = None,
    ):
        """Initialize authorization error with message and optional required permission."""
        super().__init__(
            message=message,
            error_code=error_code,
            category=ErrorCategory.AUTHORIZATION,
            severity=ErrorSeverity.ERROR,
            context=context,
        )
        self.required_permission = required_permission

        if required_permission:
            self.details["required_permission"] = required_permission

    def get_http_status_code(self) -> int:
        """Authorization errors are always 403."""
        return 403


class NetworkError(StipulationError):
    """
    Raised when network operations fail.
    """

    def __init__(
        self,
        message: str,
        error_code: str = "NETWORK_ERROR",
        endpoint: Optional[str] = None,
        status_code: Optional[int] = None,
        context: Optional[ErrorContext] = None,
        cause: Optional[Exception] = None,
    ):
        """Initialize network error with endpoint and status code details."""
        super().__init__(
            message=message,
            error_code=error_code,
            category=ErrorCategory.NETWORK,
            severity=ErrorSeverity.ERROR,
            context=context,
            cause=cause,
        )
        self.endpoint = endpoint
        self.status_code = status_code

        # Add network-specific details
        self.details.update({"endpoint": endpoint, "status_code": status_code})

    def get_http_status_code(self) -> int:
        """Network errors typically map to 502 Bad Gateway."""
        return 502


# Error code constants for consistency
class ErrorCodes:
    """Standard error codes used throughout the system."""

    # Validation errors
    MISSING_REQUIRED_FIELD = "MISSING_REQUIRED_FIELD"
    INVALID_FIELD_VALUE = "INVALID_FIELD_VALUE"
    FORBIDDEN_METHOD_PRESENT = "FORBIDDEN_METHOD_PRESENT"
    INVALID_OPENAPI_VERSION = "INVALID_OPENAPI_VERSION"
    SCHEMA_VALIDATION_FAILED = "SCHEMA_VALIDATION_FAILED"
    VERSION_ALIGNMENT_VIOLATION = "VERSION_ALIGNMENT_VIOLATION"
    TENANT_SCOPING_VIOLATION = "TENANT_SCOPING_VIOLATION"
    STIPULATION_VIOLATION = "STIPULATION_VIOLATION"

    # Transformation errors
    URL_REWRITE_FAILED = "URL_REWRITE_FAILED"
    METADATA_INJECTION_FAILED = "METADATA_INJECTION_FAILED"
    METHOD_STRIPPING_FAILED = "METHOD_STRIPPING_FAILED"
    TRANSFORMATION_CONTEXT_MISSING = "TRANSFORMATION_CONTEXT_MISSING"

    # Configuration errors
    STIPULATION_NOT_FOUND = "STIPULATION_NOT_FOUND"
    INVALID_CONFIGURATION = "INVALID_CONFIGURATION"
    CONFIGURATION_SOURCE_UNAVAILABLE = "CONFIGURATION_SOURCE_UNAVAILABLE"

    # Registry errors
    CONTRACT_NOT_FOUND = "CONTRACT_NOT_FOUND"
    CONTRACT_STORAGE_FAILED = "CONTRACT_STORAGE_FAILED"
    REGISTRY_UNAVAILABLE = "REGISTRY_UNAVAILABLE"

    # Network errors
    SERVICE_UNAVAILABLE = "SERVICE_UNAVAILABLE"
    TIMEOUT = "TIMEOUT"
    CONNECTION_FAILED = "CONNECTION_FAILED"

    # Authentication/Authorization errors
    AUTHENTICATION_FAILED = "AUTHENTICATION_FAILED"
    ACCESS_DENIED = "ACCESS_DENIED"
    INVALID_TOKEN = "INVALID_TOKEN"
    TOKEN_EXPIRED = "TOKEN_EXPIRED"


def create_error_context(
    request_id: Optional[str] = None,
    user_id: Optional[str] = None,
    service_name: Optional[str] = None,
    contract_category: Optional[str] = None,
    api_major_version: Optional[str] = None,
    stipulation_id: Optional[str] = None,
    operation: Optional[str] = None,
    **additional_data,
) -> ErrorContext:
    """
    Convenience function to create error context with common fields.
    """
    return ErrorContext(
        request_id=request_id,
        user_id=user_id,
        service_name=service_name,
        contract_category=contract_category,
        api_major_version=api_major_version,
        stipulation_id=stipulation_id,
        operation=operation,
        additional_data=additional_data,
    )
