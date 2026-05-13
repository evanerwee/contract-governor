"""
FastAPI error handlers for Contract Stipulations structured errors.

This module provides comprehensive error handling for FastAPI applications,
converting structured StipulationError exceptions into proper HTTP responses
with detailed error information for debugging and monitoring.
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

try:
    from fastapi import HTTPException, Request
    from fastapi.exception_handlers import http_exception_handler
    from fastapi.responses import JSONResponse
except ImportError:
    raise ImportError("FastAPI is required for this module. " "Install with: pip install contract-governor[server]")

from ..core.errors import (
    AuthenticationError,
    AuthorizationError,
    ConfigurationError,
    ContractNotFoundError,
    ErrorCategory,
    ErrorSeverity,
    NetworkError,
    RegistryError,
    StipulationError,
    StipulationViolationError,
    TransformationError,
    ValidationError,
)

logger = logging.getLogger(__name__)


class FastAPIErrorHandler:
    """
    Centralized error handler for FastAPI applications using Contract Stipulations.
    """

    def __init__(self, include_traceback: bool = False, log_errors: bool = True):
        """Initialize error handler with traceback and logging preferences."""
        self.include_traceback = include_traceback
        self.log_errors = log_errors

    async def stipulation_error_handler(
        self,
        request: Request,
        exc: StipulationError,
    ) -> JSONResponse:
        """Handle StipulationError exceptions and return structured JSON error responses."""
        if self.log_errors:
            self._log_error(request, exc)

        error_response = self._build_error_response(request, exc)

        return JSONResponse(
            status_code=exc.get_http_status_code(),
            content=error_response,
        )

    async def validation_error_handler(
        self,
        request: Request,
        exc: ValidationError,
    ) -> JSONResponse:
        """Handle ValidationError exceptions with field-level detail in the response."""
        if self.log_errors:
            self._log_error(request, exc)

        error_response = self._build_error_response(request, exc)
        error_response["validation_details"] = {
            "field_path": getattr(exc, "field_path", None),
            "stipulation_id": getattr(exc, "stipulation_id", None),
            "validation_errors": getattr(exc, "validation_errors", None),
        }

        # Explicit 400 is OK here (or use exc.get_http_status_code())
        return JSONResponse(status_code=400, content=error_response)

    async def transformation_error_handler(
        self,
        request: Request,
        exc: TransformationError,
    ) -> JSONResponse:
        """Handle TransformationError exceptions with transformation stage details."""
        if self.log_errors:
            self._log_error(request, exc)

        error_response = self._build_error_response(request, exc)
        error_response["transformation_details"] = {
            "stage": getattr(exc, "transformation_stage", None),
            "has_original_contract": getattr(exc, "original_contract", None) is not None,
        }

        return JSONResponse(status_code=422, content=error_response)

    async def contract_not_found_handler(
        self,
        request: Request,
        exc: ContractNotFoundError,
    ) -> JSONResponse:
        """Handle ContractNotFoundError exceptions with contract identity details."""
        if self.log_errors:
            self._log_error(request, exc)

        error_response = self._build_error_response(request, exc)
        error_response["contract_details"] = {
            "category": getattr(exc, "category_name", None),
            "api_major_version": getattr(exc, "api_major_version", None),
            "contract_type": getattr(exc, "contract_type", None),
        }

        return JSONResponse(status_code=404, content=error_response)

    async def generic_exception_handler(
        self,
        request: Request,
        exc: Exception,
    ) -> JSONResponse:
        """
        Handle generic exceptions that aren't StipulationError subclasses.
        """
        logger.error(
            "Unhandled exception in %s %s: %s",
            request.method,
            request.url,
            exc,
            exc_info=True,
            extra={
                "request_method": request.method,
                "request_url": str(request.url),
                "request_headers": dict(request.headers),
                "exception_type": type(exc).__name__,
            },
        )

        error_response = {
            "error_code": "INTERNAL_SERVER_ERROR",
            "message": "An unexpected error occurred",
            "category": ErrorCategory.SYSTEM.value,
            "severity": ErrorSeverity.CRITICAL.value,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "request_info": {
                "method": request.method,
                "url": str(request.url),
                "user_agent": request.headers.get("user-agent"),
            },
        }

        if self.include_traceback:
            error_response["details"] = {
                "exception_type": type(exc).__name__,
                "exception_message": str(exc),
            }

        return JSONResponse(status_code=500, content=error_response)

    def _build_error_response(
        self,
        request: Request,
        exc: StipulationError,
    ) -> Dict[str, Any]:
        """Build a structured error response dictionary from a StipulationError.

        Args:
            request: The incoming HTTP request that triggered the error.
            exc: The StipulationError containing error details.

        Returns:
            Dictionary with error details and request context suitable for JSON serialization.
        """
        error_response = exc.to_dict()

        error_response["request_info"] = {
            "method": request.method,
            "url": str(request.url),
            "user_agent": request.headers.get("user-agent"),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        client_ip = self._get_client_ip(request)
        if client_ip:
            error_response["request_info"]["client_ip"] = client_ip

        if not self.include_traceback and "traceback" in error_response:
            del error_response["traceback"]

        return error_response

    def _log_error(self, request: Request, exc: StipulationError) -> None:
        """Log a StipulationError with appropriate severity level and request context.

        Args:
            request: The incoming HTTP request that triggered the error.
            exc: The StipulationError to log.
        """
        if exc.severity == ErrorSeverity.CRITICAL:
            log_level = logging.CRITICAL
        elif exc.severity == ErrorSeverity.ERROR:
            log_level = logging.ERROR
        elif exc.severity == ErrorSeverity.WARNING:
            log_level = logging.WARNING
        else:
            log_level = logging.INFO

        ctx = getattr(exc, "context", None)

        def _ctx(attr: str) -> Optional[Any]:
            return getattr(ctx, attr, None) if ctx is not None else None

        log_extra = {
            "error_code": exc.error_code,
            "error_category": exc.category.value,
            "error_severity": exc.severity.value,
            "request_method": request.method,
            "request_url": str(request.url),
            "client_ip": self._get_client_ip(request),
            "user_agent": request.headers.get("user-agent"),
            "contract_category": _ctx("contract_category"),
            "api_major_version": _ctx("api_major_version"),
            "stipulation_id": _ctx("stipulation_id"),
            "operation": _ctx("operation"),
            "request_id": _ctx("request_id"),
        }

        logger.log(
            log_level,
            "%s error in %s %s: %s",
            exc.category.value.upper(),
            request.method,
            request.url,
            exc.message,
            extra=log_extra,
            exc_info=exc.cause is not None,
        )

    def _get_client_ip(self, request: Request) -> Optional[str]:
        """Extract the client IP address from the request headers or connection info.

        Checks X-Forwarded-For and X-Real-IP headers before falling back to
        the direct connection client address.

        Args:
            request: The incoming HTTP request.

        Returns:
            Client IP address string, or None if not determinable.
        """
        forwarded_for = request.headers.get("x-forwarded-for")
        if forwarded_for:
            return str(forwarded_for).split(",")[0].strip()

        real_ip = request.headers.get("x-real-ip")
        if real_ip:
            return str(real_ip)

        client = getattr(request, "client", None)
        return getattr(client, "host", None) if client else None


def register_error_handlers(
    app,
    include_traceback: bool = False,
    log_errors: bool = True,
) -> None:
    """
    Register all error handlers with a FastAPI application.
    """
    error_handler = FastAPIErrorHandler(
        include_traceback=include_traceback,
        log_errors=log_errors,
    )

    # Stipulation hierarchy
    app.add_exception_handler(ValidationError, error_handler.validation_error_handler)
    app.add_exception_handler(TransformationError, error_handler.transformation_error_handler)
    app.add_exception_handler(ContractNotFoundError, error_handler.contract_not_found_handler)
    app.add_exception_handler(StipulationViolationError, error_handler.validation_error_handler)
    app.add_exception_handler(ConfigurationError, error_handler.stipulation_error_handler)
    app.add_exception_handler(RegistryError, error_handler.stipulation_error_handler)
    app.add_exception_handler(AuthenticationError, error_handler.stipulation_error_handler)
    app.add_exception_handler(AuthorizationError, error_handler.stipulation_error_handler)
    app.add_exception_handler(NetworkError, error_handler.stipulation_error_handler)
    app.add_exception_handler(StipulationError, error_handler.stipulation_error_handler)

    # Preserve FastAPI's own HTTPException behavior
    app.add_exception_handler(HTTPException, http_exception_handler)

    # Catch-all for everything else
    app.add_exception_handler(Exception, error_handler.generic_exception_handler)


def create_http_exception_from_stipulation_error(exc: StipulationError) -> HTTPException:
    """
    Convert a StipulationError to an HTTPException for manual raising.
    """
    return HTTPException(
        status_code=exc.get_http_status_code(),
        detail=exc.to_dict(),
    )
