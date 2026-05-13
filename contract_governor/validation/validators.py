"""
Individual validator implementations for contract stipulation compliance.

Each validator focuses on a specific aspect of contract validation,
following the Single Responsibility Principle.
"""

import re
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional

from ..core.models import StipulationConfig, ValidationResult, VersionInfo


class BaseValidator(ABC):
    """
    Abstract base class for all contract validators.

    Defines the interface that all validators must implement,
    following the Template Method pattern.
    """

    @abstractmethod
    def validate(self, contract: Dict[str, Any], stipulation: StipulationConfig) -> ValidationResult:
        """
        Validate a contract against a stipulation.

        Args:
            contract: The OpenAPI contract to validate
            stipulation: The stipulation configuration to validate against

        Returns:
            ValidationResult with any errors or warnings found
        """
        pass

    def _create_result(self, stipulation: StipulationConfig, is_valid: bool = True) -> ValidationResult:
        """
        Create a base validation result for this validator.

        Args:
            stipulation: The stipulation being validated against
            is_valid: Initial validation state

        Returns:
            ValidationResult initialized for this validator
        """
        return ValidationResult(is_valid=is_valid, applied_stipulation=stipulation.stipulation_id)


class OpenAPIVersionValidator(BaseValidator):
    """
    Validates that the contract uses a supported OpenAPI specification version.

    Checks the 'openapi' field against the stipulation's required version prefix.
    """

    def validate(self, contract: Dict[str, Any], stipulation: StipulationConfig) -> ValidationResult:
        """
        Validate OpenAPI version compliance.

        Args:
            contract: The OpenAPI contract to validate
            stipulation: The stipulation configuration

        Returns:
            ValidationResult indicating version compliance
        """
        result = self._create_result(stipulation)

        # Check if openapi field exists
        if "openapi" not in contract:
            result.add_error(
                code="MISSING_OPENAPI_VERSION",
                message="Contract is missing required 'openapi' version field",
                field_path="openapi",
            )
            return result

        openapi_version = contract["openapi"]

        # Validate version format
        if not isinstance(openapi_version, str):
            result.add_error(
                code="INVALID_OPENAPI_VERSION_TYPE",
                message=f"OpenAPI version must be a string, got {type(openapi_version).__name__}",
                field_path="openapi",
            )
            return result

        # Check version against stipulation requirement
        required_prefix = stipulation.require_openapi_major
        if not openapi_version.startswith(required_prefix):
            result.add_error(
                code="UNSUPPORTED_OPENAPI_VERSION",
                message=f"OpenAPI version '{openapi_version}' does not meet requirement '{required_prefix}x'",
                field_path="openapi",
                required_version=required_prefix,
                actual_version=openapi_version,
            )

        # Validate semantic version format
        if not self._is_valid_version_format(openapi_version):
            result.add_warning(
                code="INVALID_VERSION_FORMAT",
                message=f"OpenAPI version '{openapi_version}' does not follow semantic versioning format",
                field_path="openapi",
            )

        return result

    def _is_valid_version_format(self, version: str) -> bool:
        """
        Check if version follows semantic versioning format (x.y.z).

        Args:
            version: Version string to validate

        Returns:
            True if version format is valid
        """
        version_pattern = (
            r"^\d+\.\d+\.\d+(?:-[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?$"
        )
        return bool(re.match(version_pattern, version))


class RequiredFieldsValidator(BaseValidator):
    """
    Validates that the contract contains all required fields specified in the stipulation.

    Supports nested field paths using dot notation (e.g., "info.title").
    """

    def validate(self, contract: Dict[str, Any], stipulation: StipulationConfig) -> ValidationResult:
        """
        Validate required fields compliance.

        Args:
            contract: The OpenAPI contract to validate
            stipulation: The stipulation configuration

        Returns:
            ValidationResult indicating required fields compliance
        """
        result = self._create_result(stipulation)

        # Check each required field
        for field_path in stipulation.required_fields:
            if not self._field_exists(contract, field_path):
                result.add_error(
                    code="MISSING_REQUIRED_FIELD",
                    message=f"Required field '{field_path}' is missing from contract",
                    field_path=field_path,
                )
            elif self._field_is_empty(contract, field_path):
                result.add_warning(
                    code="EMPTY_REQUIRED_FIELD",
                    message=f"Required field '{field_path}' is present but empty",
                    field_path=field_path,
                )

        return result

    def _field_exists(self, contract: Dict[str, Any], field_path: str) -> bool:
        """
        Check if a field exists in the contract using dot notation.

        Args:
            contract: The contract to check
            field_path: Dot-separated path to the field (e.g., "info.title")

        Returns:
            True if field exists
        """
        try:
            current = contract
            for part in field_path.split("."):
                if not isinstance(current, dict) or part not in current:
                    return False
                current = current[part]
            return True
        except (KeyError, TypeError):
            return False

    def _field_is_empty(self, contract: Dict[str, Any], field_path: str) -> bool:
        """
        Check if a field exists but is empty.

        Args:
            contract: The contract to check
            field_path: Dot-separated path to the field

        Returns:
            True if field exists but is empty
        """
        try:
            current = contract
            for part in field_path.split("."):
                current = current[part]

            # Check various empty conditions
            if current is None:
                return True
            if isinstance(current, str) and not current.strip():
                return True
            if isinstance(current, (list, dict)) and len(current) == 0:
                return True

            return False
        except (KeyError, TypeError):
            return False


class ForbiddenMethodsValidator(BaseValidator):
    """
    Validates that the contract does not contain HTTP methods forbidden by the stipulation.

    Checks all paths in the contract for forbidden methods.
    """

    def validate(self, contract: Dict[str, Any], stipulation: StipulationConfig) -> ValidationResult:
        """
        Validate forbidden methods compliance.

        Args:
            contract: The OpenAPI contract to validate
            stipulation: The stipulation configuration

        Returns:
            ValidationResult indicating forbidden methods compliance
        """
        result = self._create_result(stipulation)

        # Skip validation if no methods are forbidden
        if not stipulation.forbid_methods:
            return result

        # Normalize forbidden methods to lowercase
        forbidden_methods = [method.lower() for method in stipulation.forbid_methods]

        # Check paths section
        paths = contract.get("paths", {})
        if not isinstance(paths, dict):
            result.add_warning(
                code="INVALID_PATHS_SECTION", message="Paths section is not a valid object", field_path="paths"
            )
            return result

        # Check each path for forbidden methods
        for path, path_obj in paths.items():
            if not isinstance(path_obj, dict):
                continue

            for method in path_obj.keys():
                # Skip non-HTTP method keys (like parameters, summary, etc.)
                if method.lower() not in ["get", "post", "put", "patch", "delete", "head", "options", "trace"]:
                    continue

                if method.lower() in forbidden_methods:
                    result.add_error(
                        code="FORBIDDEN_METHOD_PRESENT",
                        message=f"Forbidden HTTP method '{method.upper()}' found in path '{path}'",
                        field_path=f"paths.{path}.{method}",
                        forbidden_method=method.upper(),
                        path=path,
                    )

        return result


class TenantScopingValidator(BaseValidator):
    """
    Validates tenant scoping requirements for APIs that require scope parameters.

    Ensures that tenant-scoped APIs have proper scope parameters in proxy format.
    """

    def validate(self, contract: Dict[str, Any], stipulation: StipulationConfig) -> ValidationResult:
        """
        Validate tenant scoping compliance.

        Args:
            contract: The OpenAPI contract to validate
            stipulation: The stipulation configuration

        Returns:
            ValidationResult indicating tenant scoping compliance
        """
        result = self._create_result(stipulation)

        # Only validate if scope parameter is required
        if not stipulation.requires_scope_parameter:
            return result

        # Check if proxy prefix format contains scope parameters
        proxy_format = stipulation.proxy_prefix_format
        if proxy_format is None:
            result.add_error(
                code="MISSING_SCOPE_PARAMETER",
                message="Tenant-scoped API missing proxy_prefix_format",
                field_path="proxy_prefix_format",
            )
            return result
        scope_parameters = ["{tenant_id}", "{scope_id}", "{organization_id}"]

        has_scope_param = any(param in proxy_format for param in scope_parameters)

        if not has_scope_param:
            result.add_error(
                code="MISSING_SCOPE_PARAMETER",
                message=f"Tenant-scoped API missing scope parameter in proxy_prefix_format: {proxy_format}",
                field_path="proxy_prefix_format",
                proxy_format=proxy_format,
                expected_parameters=scope_parameters,
            )

        # Validate that the proxy format is well-formed
        if not self._is_valid_proxy_format(proxy_format):
            result.add_error(
                code="INVALID_PROXY_FORMAT",
                message=f"Proxy prefix format is not well-formed: {proxy_format}",
                field_path="proxy_prefix_format",
                proxy_format=proxy_format,
            )

        # Check for tenant-specific contract requirements
        self._validate_tenant_contract_requirements(contract, stipulation, result)

        return result

    def _is_valid_proxy_format(self, proxy_format: str) -> bool:
        """
        Validate that proxy format is well-formed.

        Args:
            proxy_format: The proxy format string to validate

        Returns:
            True if format is valid
        """
        if not proxy_format.startswith("/"):
            return False

        # Check for balanced braces in parameters
        open_braces = proxy_format.count("{")
        close_braces = proxy_format.count("}")

        return open_braces == close_braces

    def _validate_tenant_contract_requirements(
        self, contract: Dict[str, Any], stipulation: StipulationConfig, result: ValidationResult
    ) -> None:
        """
        Validate contract-specific requirements for tenant-scoped APIs.

        Args:
            contract: The contract to validate
            stipulation: The stipulation configuration
            result: The validation result to update
        """
        # Check if contract has tenant-aware security schemes
        if "components" in contract and "securitySchemes" in contract["components"]:
            security_schemes = contract["components"]["securitySchemes"]

            # Look for tenant-aware authentication
            has_tenant_auth = False
            for scheme_name, scheme in security_schemes.items():
                if isinstance(scheme, dict):
                    # Check for tenant-related fields in security scheme
                    scheme_str = str(scheme).lower()
                    if any(keyword in scheme_str for keyword in ["tenant", "scope", "organization"]):
                        has_tenant_auth = True
                        break

            if not has_tenant_auth:
                result.add_warning(
                    code="MISSING_TENANT_AUTHENTICATION",
                    message="Tenant-scoped API should include tenant-aware authentication schemes",
                    field_path="components.securitySchemes",
                )


class VersionAlignmentValidator(BaseValidator):
    """
    Validates version alignment between API major version and contract version.

    Ensures that contract versions are consistent with their API major version
    when version alignment is enforced by the stipulation.
    """

    def validate(self, contract: Dict[str, Any], stipulation: StipulationConfig) -> ValidationResult:
        """
        Validate version alignment compliance.

        Args:
            contract: The OpenAPI contract to validate
            stipulation: The stipulation configuration

        Returns:
            ValidationResult indicating version alignment compliance
        """
        result = self._create_result(stipulation)

        # Skip validation if version alignment is not enforced
        if not stipulation.enforce_version_alignment:
            return result

        # Extract version information
        version_info = self._extract_version_info(contract, stipulation)

        if not version_info:
            result.add_error(
                code="MISSING_VERSION_INFORMATION",
                message="Cannot validate version alignment: missing version information",
                field_path="info.version",
            )
            return result

        # Validate version consistency
        if not version_info.is_compatible:
            errors = version_info.get_consistency_errors()
            for error in errors:
                result.add_error(
                    code="VERSION_ALIGNMENT_VIOLATION",
                    message=error,
                    field_path="info.version",
                    api_major_version=version_info.api_major_version,
                    contract_version=version_info.contract_version,
                )

        # Additional version format validations
        self._validate_version_formats(version_info, result)

        return result

    def _extract_version_info(self, contract: Dict[str, Any], stipulation: StipulationConfig) -> Optional[VersionInfo]:
        """
        Extract version information from contract and stipulation.

        Args:
            contract: The contract to extract versions from
            stipulation: The stipulation configuration

        Returns:
            VersionInfo object or None if extraction fails
        """
        try:
            # Get contract version from info.version
            contract_version = contract.get("info", {}).get("version", "")
            if not contract_version:
                return None

            # Get OpenAPI version
            openapi_version = contract.get("openapi", "")

            # For this validator, we need to infer API major version
            # In a real implementation, this would come from the context
            # For now, we'll extract it from the contract version
            api_major_version = self._infer_api_major_version(contract_version)

            return VersionInfo(
                api_major_version=api_major_version, contract_version=contract_version, openapi_version=openapi_version
            )
        except Exception:
            return None

    def _infer_api_major_version(self, contract_version: str) -> str:
        """
        Infer API major version from contract version.

        Args:
            contract_version: The contract version string

        Returns:
            Inferred API major version (e.g., "v1")
        """
        # Extract major version number from contract version
        parts = contract_version.split(".")
        if parts and parts[0].isdigit():
            return f"v{parts[0]}"
        return "v1"  # Default fallback

    def _validate_version_formats(self, version_info: VersionInfo, result: ValidationResult) -> None:
        """
        Validate that version formats are correct.

        Args:
            version_info: The version information to validate
            result: The validation result to update
        """
        # Validate contract version format (semantic versioning)
        if not self._is_valid_semver(version_info.contract_version):
            result.add_warning(
                code="INVALID_CONTRACT_VERSION_FORMAT",
                message=f"Contract version '{version_info.contract_version}' does not follow semantic versioning",
                field_path="info.version",
            )

        # Validate API major version format
        if not version_info.api_major_version.startswith("v"):
            result.add_warning(
                code="INVALID_API_MAJOR_FORMAT",
                message=f"API major version '{version_info.api_major_version}' should start with 'v'",
                api_major_version=version_info.api_major_version,
            )

    def _is_valid_semver(self, version: str) -> bool:
        """
        Check if version follows semantic versioning format.

        Args:
            version: Version string to validate

        Returns:
            True if version is valid semantic version
        """
        semver_pattern = (
            r"^(\d+)\.(\d+)\.(\d+)(?:-([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?(?:\+([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?$"
        )
        return bool(re.match(semver_pattern, version))
