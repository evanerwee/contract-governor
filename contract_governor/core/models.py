"""
Core data models for the Contract Stipulations system.

This module defines the data structures used throughout the system following
the Single Responsibility Principle - each model has a clear, focused purpose.
"""

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, cast


class ExposurePolicy(str, Enum):
    """Enumeration of supported exposure policies for API contracts."""
    TENANT_SCOPED = "tenant-scoped"
    GLOBAL_CONTROL_PLANE = "global-control-plane"
    PRIVATE = "private"


@dataclass
class StipulationConfig:
    """
    Configuration object defining how a contract should be validated,
    transformed, and exposed.

    This follows the Single Responsibility Principle by containing only
    configuration data and validation logic for stipulation policies.
    """

    # Core exposure configuration
    exposure_policy: ExposurePolicy
    proxy_prefix_format: Optional[str] = None  # URL template with placeholders like "/tenant/{tenant_id}/{category}/{api_major}"
    requires_scope_parameter: bool = False  # Whether tenant/scope parameter is required in URL

    # Server URL configuration - List of named server URLs with variable substitution
    server_urls: Optional[List[Dict[str, str]]] = None  # List of server URLs: [{"name": "EXTERNAL", "url_template": "https://${VAR}", "description": "..."}]

    # Method and field restrictions
    forbid_methods: List[str] = field(default_factory=list)  # HTTP methods to strip
    required_fields: List[str] = field(default_factory=list)  # Required OpenAPI fields

    # Version requirements
    require_openapi_major: str = "3."  # Required OpenAPI version prefix
    enforce_version_alignment: bool = True  # Whether to enforce contract/API major version alignment

    # Metadata injection configuration
    inject_metadata: bool = True  # Whether to inject metadata block
    metadata_block: Dict[str, Any] = field(default_factory=dict)  # Metadata to inject
    extension_namespace: str = "x-governance"  # Extension namespace for metadata

    # Catalog visibility
    catalog_default_visible: bool = True  # Default catalog visibility

    # Implementation discovery
    implementation_module: Optional[str] = None  # Module path for implementation discovery (e.g., "factory")
    implementation_router_class: Optional[str] = None  # Router class name for stipulation-guided discovery

    # Stipulation identification
    stipulation_id: str = ""  # Unique identifier for this stipulation
    stipulation_version: str = "1.0.0"  # Version of this stipulation policy
    last_updated: Optional[str] = None  # ISO 8601 timestamp of last update

    # Deployment targeting - controls which pods mount this contract
    mount_on: Optional[List[str]] = None  # Only mount on these deployment roles (e.g., ["control-plane-controller"])
    exclude_from: Optional[List[str]] = None  # Don't mount on these deployment roles (e.g., ["control-plane-api"])

    def __post_init__(self):
        """Validate stipulation configuration consistency after initialization."""
        self._validate_configuration()

        # Generate stipulation_id if not provided
        if not self.stipulation_id:
            self.stipulation_id = self._generate_stipulation_id()

    def _validate_configuration(self) -> None:
        """Validate that the stipulation configuration is internally consistent."""
        errors = []

        # Validate exposure policy and scope parameter consistency
        if self.exposure_policy == ExposurePolicy.TENANT_SCOPED:
            if self.requires_scope_parameter:
                if not self.proxy_prefix_format or not any(param in self.proxy_prefix_format for param in ["{tenant_id}", "{scope_id}", "{organization_id}"]):
                    errors.append("Tenant-scoped policy requires scope parameter in proxy_prefix_format")

        # Validate proxy prefix format (only if provided)
        if self.proxy_prefix_format and not self.proxy_prefix_format.startswith("/"):
            errors.append("proxy_prefix_format must start with '/' when provided")

        # Validate required fields
        if not self.required_fields:
            self.required_fields = ["openapi", "info.title", "info.version", "paths"]

        # Validate OpenAPI version requirement
        if not self.require_openapi_major:
            errors.append("require_openapi_major cannot be empty")

        # Validate extension namespace
        if self.inject_metadata and not self.extension_namespace:
            errors.append("extension_namespace required when inject_metadata is True")

        if self.extension_namespace and not self.extension_namespace.startswith("x-"):
            errors.append("extension_namespace must start with 'x-' per OpenAPI specification")

        # Validate HTTP methods
        valid_methods = {"get", "post", "put", "patch", "delete", "head", "options", "trace"}
        invalid_methods = [method.lower() for method in self.forbid_methods if method.lower() not in valid_methods]
        if invalid_methods:
            errors.append(f"Invalid HTTP methods in forbid_methods: {invalid_methods}")

        if errors:
            raise ValueError(f"Stipulation configuration validation failed: {'; '.join(errors)}")

    def _generate_stipulation_id(self) -> str:
        """Generate a unique stipulation ID based on configuration content."""
        # Create a hash of the key configuration elements
        config_str = f"{self.exposure_policy}:{self.proxy_prefix_format}:{self.requires_scope_parameter}"
        config_hash = hashlib.sha256(config_str.encode()).hexdigest()[:8]
        return f"stipulation-{config_hash}"

    def get_stipulation_hash(self) -> str:
        """Generate a hash of the entire stipulation for non-repudiation tracking."""
        # Create a deterministic representation of the stipulation
        stipulation_dict = {
            "exposure_policy": self.exposure_policy.value if isinstance(self.exposure_policy, ExposurePolicy) else self.exposure_policy,
            "proxy_prefix_format": self.proxy_prefix_format,
            "requires_scope_parameter": self.requires_scope_parameter,
            "forbid_methods": sorted(self.forbid_methods),
            "required_fields": sorted(self.required_fields),
            "require_openapi_major": self.require_openapi_major,
            "enforce_version_alignment": self.enforce_version_alignment,
            "inject_metadata": self.inject_metadata,
            "metadata_block": self.metadata_block,
            "extension_namespace": self.extension_namespace,
            "catalog_default_visible": self.catalog_default_visible,
            "stipulation_version": self.stipulation_version
        }

        # Create deterministic JSON and hash it
        stipulation_json = json.dumps(stipulation_dict, sort_keys=True, separators=(',', ':'))
        return hashlib.sha256(stipulation_json.encode()).hexdigest()

    def is_compatible_with(self, other: 'StipulationConfig') -> bool:
        """Check if this stipulation is compatible with another stipulation."""
        # Two stipulations are compatible if they have the same core policy
        return (
            self.exposure_policy == other.exposure_policy and
            self.proxy_prefix_format == other.proxy_prefix_format and
            self.requires_scope_parameter == other.requires_scope_parameter
        )

    def should_mount_for_role(self, deployment_role: str) -> bool:
        """Check if this contract should be mounted for the given deployment role.

        Logic:
        - If mount_on is set: only mount if role is in the list
        - If exclude_from is set: mount unless role is in the list
        - If neither is set: mount everywhere (backward compatible)

        Args:
            deployment_role: The deployment role from DEPLOYMENT_ROLE env var

        Returns:
            True if the contract should be mounted, False otherwise
        """
        if not deployment_role:
            return True  # No role specified = mount everything

        if self.mount_on:
            return deployment_role in self.mount_on

        if self.exclude_from:
            return deployment_role not in self.exclude_from

        return True  # Default: mount everywhere


@dataclass
class StipulationRegistry:
    """
    Registry for storing and retrieving stipulation configurations.

    Follows Single Responsibility Principle by focusing only on stipulation
    storage and retrieval operations.
    """

    _stipulations: Dict[str, StipulationConfig] = field(default_factory=dict)

    def register_stipulation(self, category: str, api_major: str, config: StipulationConfig) -> None:
        """Register a stipulation configuration for a specific API category and major version."""
        key = self._make_key(category, api_major)

        # Validate the configuration before storing
        if not isinstance(config, StipulationConfig):
            raise TypeError("config must be a StipulationConfig instance")

        self._stipulations[key] = config

    def get_stipulation(self, category: str, api_major: str) -> Optional[StipulationConfig]:
        """Retrieve a stipulation configuration for a specific API category and major version."""
        key = self._make_key(category, api_major)
        return self._stipulations.get(key)

    def has_stipulation(self, category: str, api_major: str) -> bool:
        """Check if a stipulation exists for the given category and API major version."""
        key = self._make_key(category, api_major)
        return key in self._stipulations

    def list_stipulations(self) -> Dict[str, StipulationConfig]:
        """List all registered stipulations."""
        return self._stipulations.copy()

    def remove_stipulation(self, category: str, api_major: str) -> bool:
        """Remove a stipulation configuration. Returns True if removed, False if not found."""
        key = self._make_key(category, api_major)
        if key in self._stipulations:
            del self._stipulations[key]
            return True
        return False

    def clear(self) -> None:
        """Clear all stipulations from the registry."""
        self._stipulations.clear()

    def get_stipulations_by_category(self, category: str) -> Dict[str, StipulationConfig]:
        """Get all stipulations for a specific category."""
        result = {}
        for key, stipulation in self._stipulations.items():
            stored_category, api_major = self._parse_key(key)
            if stored_category == category:
                result[api_major] = stipulation
        return result

    def get_stipulations_by_policy(self, policy: ExposurePolicy) -> Dict[str, StipulationConfig]:
        """Get all stipulations with a specific exposure policy."""
        result = {}
        for key, stipulation in self._stipulations.items():
            if stipulation.exposure_policy == policy:
                result[key] = stipulation
        return result

    @staticmethod
    def _make_key(category: str, api_major: str) -> str:
        """Create a registry key from category and API major version."""
        if not category or not api_major:
            raise ValueError("Both category and api_major must be non-empty strings")
        return f"{category}:{api_major}"

    @staticmethod
    def _parse_key(key: str) -> tuple[str, str]:
        """Parse a registry key back into category and API major version."""
        parts = key.split(":", 1)
        if len(parts) != 2:
            raise ValueError(f"Invalid registry key format: {key}")
        return parts[0], parts[1]

@dataclass
class VersionInfo:
    """
    Version information extracted from OpenAPI contracts.

    Handles the distinction between API major version (URL routing)
    and contract version (semantic versioning).
    """

    api_major_version: str      # Extracted from file path or URL (v1, v2)
    contract_version: str       # From OpenAPI info.version (1.0.2)
    openapi_version: str        # From OpenAPI openapi field (3.0.3)
    is_compatible: bool = True  # Whether versions are consistent

    def __post_init__(self):
        """Validate version consistency after initialization."""
        self.is_compatible = self._validate_consistency()

    def _validate_consistency(self) -> bool:
        """Validate that API major and contract versions are consistent."""
        if not self.api_major_version or not self.contract_version:
            return False

        # Extract numeric part from API major version (v1 -> 1)
        api_major_num = self.api_major_version.lstrip('v')

        # Check if contract version starts with the API major number
        return self.contract_version.startswith(api_major_num + '.')

    def get_consistency_errors(self) -> List[str]:
        """Get detailed consistency validation errors."""
        errors = []

        if not self.api_major_version:
            errors.append("API major version is required")
        elif not self.api_major_version.startswith('v'):
            errors.append(f"API major version should start with 'v': {self.api_major_version}")

        if not self.contract_version:
            errors.append("Contract version is required")
        elif not self._is_valid_semver(self.contract_version):
            errors.append(f"Contract version is not valid semantic version: {self.contract_version}")

        if not self.openapi_version:
            errors.append("OpenAPI version is required")
        elif not self.openapi_version.startswith('3.'):
            errors.append(f"Only OpenAPI 3.x is supported: {self.openapi_version}")

        if not self._validate_consistency():
            api_major_num = self.api_major_version.lstrip('v') if self.api_major_version else ""
            errors.append(
                f"Contract version {self.contract_version} incompatible with "
                f"API major {self.api_major_version} (expected {api_major_num}.x.x)"
            )

        return errors

    @staticmethod
    def _is_valid_semver(version: str) -> bool:
        """Check if a version string follows semantic versioning."""
        import re
        semver_pattern = r'^(\d+)\.(\d+)\.(\d+)(?:-([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?(?:\+([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?$'
        return bool(re.match(semver_pattern, version))


@dataclass
class RawContractRecord:
    """
    Raw contract record from backend service - NEVER exposed to clients.

    This represents the internal, unprocessed contract as received from
    backend services. Contains internal URLs and potentially unsafe methods.
    """

    category: str                           # API category (e.g., "evidence-query")
    api_major_version: str                  # API major version (e.g., "v1")
    contract_version: str                   # Contract semantic version (e.g., "1.0.2")
    source_service: str                     # Service that provided the contract
    raw_openapi_spec: Dict[str, Any]        # Raw OpenAPI specification
    contract_file_path: str                 # Original file path
    received_at: datetime                   # When contract was received

    # Optional metadata
    service_version: Optional[str] = None   # Version of the source service
    environment: Optional[str] = None       # Environment (dev, staging, prod)
    metadata: Dict[str, Any] = field(default_factory=dict)  # Additional metadata

    def __post_init__(self):
        """Validate the raw contract record after initialization."""
        self._validate_record()

    def _validate_record(self) -> None:
        """Validate that the raw contract record is properly formed."""
        errors = []

        if not self.category:
            errors.append("category is required")

        if not self.api_major_version:
            errors.append("api_major_version is required")

        if not self.contract_version:
            errors.append("contract_version is required")

        if not self.source_service:
            errors.append("source_service is required")

        if not self.raw_openapi_spec:
            errors.append("raw_openapi_spec is required")
        elif not isinstance(self.raw_openapi_spec, dict):
            errors.append("raw_openapi_spec must be a dictionary")

        if not self.contract_file_path:
            errors.append("contract_file_path is required")

        if not self.received_at:
            errors.append("received_at is required")

        if errors:
            raise ValueError(f"Raw contract record validation failed: {'; '.join(errors)}")

    def get_version_info(self) -> VersionInfo:
        """Extract version information from the raw contract."""
        openapi_version = self.raw_openapi_spec.get('openapi', '')
        return VersionInfo(
            api_major_version=self.api_major_version,
            contract_version=self.contract_version,
            openapi_version=openapi_version
        )

    def get_contract_title(self) -> str:
        """Get the contract title from the OpenAPI spec."""
        # Safe: .get() with str default always returns str
        return cast(str, self.raw_openapi_spec.get('info', {}).get('title', f"{self.category} API"))

    def get_contract_description(self) -> str:
        """Get the contract description from the OpenAPI spec."""
        # Safe: .get() with str default always returns str
        return cast(str, self.raw_openapi_spec.get('info', {}).get('description', ''))

    def get_processing_metadata(self) -> Dict[str, Any]:
        """Get comprehensive processing metadata for debugging."""
        return {
            "category": self.category,
            "api_major_version": self.api_major_version,
            "contract_version": self.contract_version,
            "source_service": self.source_service,
            "contract_file_path": self.contract_file_path,
            "received_at": self.received_at.isoformat(),
            "service_version": self.service_version,
            "environment": self.environment,
            "metadata": self.metadata
        }


@dataclass
class ExposedContractRecord:
    """
    Validated, transformed contract safe for client exposure.

    This represents a contract that has been validated against stipulations,
    transformed with proxy URLs, and stamped with audit metadata.
    """

    category: str                           # API category
    api_major_version: str                  # API major version
    contract_version: str                   # Contract semantic version
    source_service: str                     # Original source service
    exposed_openapi_spec: Dict[str, Any]    # Transformed OpenAPI spec with proxy URLs
    openapi_mount_path: str                 # Path where spec is served (e.g., "/contracts/evidence-query/v1/openapi.json")
    proxy_prefix: str                       # Proxy URL prefix (e.g., "/tenant/{tenant_id}/evidence-query/v1")
    stipulation_applied: str                # ID of applied stipulation
    stipulation_hash: str                   # Hash of StipulationConfig used
    exposed_at: datetime                    # When contract was exposed
    audit_metadata: Dict[str, Any]          # Audit and governance metadata

    # Optional fields
    documentation_url: Optional[str] = None  # URL to Scalar documentation
    catalog_visible: bool = True            # Whether visible in catalog
    tags: List[str] = field(default_factory=list)  # Tags for categorization

    def __post_init__(self):
        """Validate the exposed contract record after initialization."""
        self._validate_record()

    def _validate_record(self) -> None:
        """Validate that the exposed contract record is properly formed."""
        errors = []

        if not self.category:
            errors.append("category is required")

        if not self.api_major_version:
            errors.append("api_major_version is required")

        if not self.contract_version:
            errors.append("contract_version is required")

        if not self.source_service:
            errors.append("source_service is required")

        if not self.exposed_openapi_spec:
            errors.append("exposed_openapi_spec is required")
        elif not isinstance(self.exposed_openapi_spec, dict):
            errors.append("exposed_openapi_spec must be a dictionary")

        if not self.openapi_mount_path:
            errors.append("openapi_mount_path is required")
        elif not self.openapi_mount_path.startswith("/"):
            errors.append("openapi_mount_path must start with '/'")

        if not self.proxy_prefix:
            errors.append("proxy_prefix is required")
        elif not self.proxy_prefix.startswith("/"):
            errors.append("proxy_prefix must start with '/'")

        if not self.stipulation_applied:
            errors.append("stipulation_applied is required")

        if not self.stipulation_hash:
            errors.append("stipulation_hash is required")

        if not self.exposed_at:
            errors.append("exposed_at is required")

        if not self.audit_metadata:
            errors.append("audit_metadata is required")
        elif not isinstance(self.audit_metadata, dict):
            errors.append("audit_metadata must be a dictionary")

        if errors:
            raise ValueError(f"Exposed contract record validation failed: {'; '.join(errors)}")

    def get_version_info(self) -> VersionInfo:
        """Extract version information from the exposed contract."""
        openapi_version = self.exposed_openapi_spec.get('openapi', '')
        return VersionInfo(
            api_major_version=self.api_major_version,
            contract_version=self.contract_version,
            openapi_version=openapi_version
        )

    def get_contract_title(self) -> str:
        """Get the contract title from the OpenAPI spec."""
        # Safe: .get() with str default always returns str
        return cast(str, self.exposed_openapi_spec.get('info', {}).get('title', f"{self.category} API"))

    def get_contract_description(self) -> str:
        """Get the contract description from the OpenAPI spec."""
        # Safe: .get() with str default always returns str
        return cast(str, self.exposed_openapi_spec.get('info', {}).get('description', ''))

    def get_processing_metadata(self) -> Dict[str, Any]:
        """Get comprehensive processing metadata for debugging."""
        return {
            "category": self.category,
            "api_major_version": self.api_major_version,
            "contract_version": self.contract_version,
            "source_service": self.source_service,
            "stipulation_applied": self.stipulation_applied,
            "stipulation_hash": self.stipulation_hash,
            "exposed_at": self.exposed_at.isoformat(),
            "proxy_prefix": self.proxy_prefix,
            "openapi_mount_path": self.openapi_mount_path,
            "catalog_visible": self.catalog_visible,
            "is_tenant_scoped": self.is_tenant_scoped(),
            "tags": self.tags,
            "audit_metadata": self.audit_metadata
        }

    def get_documentation_url(self) -> str:
        """Get the Scalar documentation URL for this contract."""
        if self.documentation_url:
            return self.documentation_url

        # Generate default documentation URL
        base_path = self.openapi_mount_path.replace('/openapi.json', '')
        return f"{base_path}/docs"

    def is_tenant_scoped(self) -> bool:
        """Check if this contract requires tenant scoping."""
        return "{tenant_id}" in self.proxy_prefix or "{scope_id}" in self.proxy_prefix

    def get_proxy_url_for_tenant(self, tenant_id: str, **kwargs) -> str:
        """Generate the actual proxy URL for a specific tenant."""
        if not self.is_tenant_scoped():
            return self.proxy_prefix

        # Replace placeholders in proxy prefix
        url_params = {"tenant_id": tenant_id, **kwargs}
        try:
            return self.proxy_prefix.format(**url_params)
        except KeyError as e:
            raise ValueError(f"Missing required parameter for proxy URL: {e}")


@dataclass
class TransformContext:
    """
    Context information for contract transformation operations.

    Contains all the information needed to transform a raw contract
    into an exposed contract with proper proxy URLs and metadata.
    """

    # Core transformation parameters
    category: str                           # API category being transformed
    api_major_version: str                  # Target API major version
    contract_version: str                   # Specific contract version
    gateway_base_url: str                   # Base URL of the gateway service

    # Scope and routing parameters
    scope_parameters: Dict[str, str] = field(default_factory=dict)  # e.g., {"tenant_id": "acme"}
    target_audience: str = "public"         # "public", "internal", "partner"

    # Metadata and audit information
    transformation_timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata_overrides: Dict[str, Any] = field(default_factory=dict)  # Custom metadata to inject

    # Optional context
    source_service: Optional[str] = None    # Service providing the contract
    environment: Optional[str] = None       # Target environment
    request_id: Optional[str] = None        # Request ID for tracing

    def __post_init__(self):
        """Validate the transformation context after initialization."""
        self._validate_context()

    def _validate_context(self) -> None:
        """Validate that the transformation context is properly formed."""
        errors = []

        if not self.category:
            errors.append("category is required")

        if not self.api_major_version:
            errors.append("api_major_version is required")

        if not self.contract_version:
            errors.append("contract_version is required")

        if not self.gateway_base_url:
            errors.append("gateway_base_url is required")
        elif not self.gateway_base_url.startswith(('http://', 'https://')):
            errors.append("gateway_base_url must be a valid HTTP/HTTPS URL")

        if self.target_audience not in ["public", "internal", "partner"]:
            errors.append("target_audience must be one of: public, internal, partner")

        if errors:
            raise ValueError(f"Transform context validation failed: {'; '.join(errors)}")

    def get_proxy_base_url(self) -> str:
        """Get the base URL for proxy operations."""
        return self.gateway_base_url.rstrip('/')

    def has_scope_parameter(self, param_name: str) -> bool:
        """Check if a specific scope parameter is available."""
        return param_name in self.scope_parameters

    def get_scope_parameter(self, param_name: str, default: Optional[str] = None) -> Optional[str]:
        """Get a specific scope parameter value."""
        return self.scope_parameters.get(param_name, default)

    def add_metadata_override(self, key: str, value: Any) -> None:
        """Add a metadata override for the transformation."""
        self.metadata_overrides[key] = value

    def create_audit_context(self) -> Dict[str, Any]:
        """Create audit context information for governance tracking."""
        return {
            "transformation_id": f"{self.category}:{self.api_major_version}:{self.transformation_timestamp.isoformat()}",
            "category": self.category,
            "api_major_version": self.api_major_version,
            "contract_version": self.contract_version,
            "target_audience": self.target_audience,
            "transformation_timestamp": self.transformation_timestamp.isoformat(),
            "gateway_base_url": self.gateway_base_url,
            "scope_parameters": self.scope_parameters.copy(),
            "source_service": self.source_service,
            "environment": self.environment,
            "request_id": self.request_id
        }


@dataclass
class ValidationError:
    """
    Represents a validation error with detailed context.
    """

    code: str                               # Error code (e.g., "MISSING_REQUIRED_FIELD")
    message: str                            # Human-readable error message
    field_path: Optional[str] = None        # Path to the field that caused the error
    stipulation_id: Optional[str] = None    # ID of the stipulation that was violated
    severity: str = "error"                 # "error", "warning", "info"
    context: Dict[str, Any] = field(default_factory=dict)  # Additional context

    def __post_init__(self):
        """Validate the error object after initialization."""
        if self.severity not in ["error", "warning", "info"]:
            self.severity = "error"

    def to_dict(self) -> Dict[str, Any]:
        """Convert the error to a dictionary representation."""
        return {
            "code": self.code,
            "message": self.message,
            "field_path": self.field_path,
            "stipulation_id": self.stipulation_id,
            "severity": self.severity,
            "context": self.context
        }


@dataclass
class ValidationWarning:
    """
    Represents a validation warning with detailed context.
    """

    code: str                               # Warning code
    message: str                            # Human-readable warning message
    field_path: Optional[str] = None        # Path to the field that caused the warning
    stipulation_id: Optional[str] = None    # ID of the stipulation
    context: Dict[str, Any] = field(default_factory=dict)  # Additional context

    def to_dict(self) -> Dict[str, Any]:
        """Convert the warning to a dictionary representation."""
        return {
            "code": self.code,
            "message": self.message,
            "field_path": self.field_path,
            "stipulation_id": self.stipulation_id,
            "context": self.context
        }


@dataclass
class ValidationResult:
    """
    Result of contract validation with structured error and warning reporting.

    Provides comprehensive feedback about stipulation compliance and
    contract validation status.
    """

    is_valid: bool                          # Whether validation passed
    errors: List[ValidationError] = field(default_factory=list)  # Validation errors
    warnings: List[ValidationWarning] = field(default_factory=list)  # Validation warnings
    applied_stipulation: Optional[str] = None  # ID of the stipulation that was applied
    validation_timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    # Validation metadata
    validator_version: Optional[str] = None  # Version of the validator used
    validation_duration_ms: Optional[int] = None  # Time taken for validation
    contract_category: Optional[str] = None  # Category of the validated contract

    def __post_init__(self):
        """Ensure validation result consistency."""
        # If there are errors, validation should not be valid
        if self.errors and self.is_valid:
            self.is_valid = False

    def add_error(self, code: str, message: str, field_path: Optional[str] = None,
                  stipulation_id: Optional[str] = None, **context) -> None:
        """Add a validation error to the result."""
        error = ValidationError(
            code=code,
            message=message,
            field_path=field_path,
            stipulation_id=stipulation_id or self.applied_stipulation,
            context=context
        )
        self.errors.append(error)
        self.is_valid = False

    def add_warning(self, code: str, message: str, field_path: Optional[str] = None,
                    stipulation_id: Optional[str] = None, **context) -> None:
        """Add a validation warning to the result."""
        warning = ValidationWarning(
            code=code,
            message=message,
            field_path=field_path,
            stipulation_id=stipulation_id or self.applied_stipulation,
            context=context
        )
        self.warnings.append(warning)

    def has_errors(self) -> bool:
        """Check if the validation result has any errors."""
        return len(self.errors) > 0

    def has_warnings(self) -> bool:
        """Check if the validation result has any warnings."""
        return len(self.warnings) > 0

    def get_error_count(self) -> int:
        """Get the total number of errors."""
        return len(self.errors)

    def get_warning_count(self) -> int:
        """Get the total number of warnings."""
        return len(self.warnings)

    def get_errors_by_code(self, code: str) -> List[ValidationError]:
        """Get all errors with a specific error code."""
        return [error for error in self.errors if error.code == code]

    def get_warnings_by_code(self, code: str) -> List[ValidationWarning]:
        """Get all warnings with a specific warning code."""
        return [warning for warning in self.warnings if warning.code == code]

    def get_summary(self) -> Dict[str, Any]:
        """Get a summary of the validation result."""
        return {
            "is_valid": self.is_valid,
            "error_count": self.get_error_count(),
            "warning_count": self.get_warning_count(),
            "applied_stipulation": self.applied_stipulation,
            "validation_timestamp": self.validation_timestamp.isoformat(),
            "validator_version": self.validator_version,
            "validation_duration_ms": self.validation_duration_ms,
            "contract_category": self.contract_category
        }

    def to_dict(self) -> Dict[str, Any]:
        """Convert the validation result to a dictionary representation."""
        return {
            "is_valid": self.is_valid,
            "errors": [error.to_dict() for error in self.errors],
            "warnings": [warning.to_dict() for warning in self.warnings],
            "applied_stipulation": self.applied_stipulation,
            "validation_timestamp": self.validation_timestamp.isoformat(),
            "validator_version": self.validator_version,
            "validation_duration_ms": self.validation_duration_ms,
            "contract_category": self.contract_category,
            "summary": self.get_summary()
        }


@dataclass
class AuditMetadata:
    """
    Audit metadata structure for governance tracking.

    Contains comprehensive audit information that gets injected
    into exposed contracts for compliance and tracking purposes.
    """

    # Core audit information
    capability_category: str                # API category
    api_major_version: str                  # API major version
    contract_version: str                   # Contract version
    stipulation_id: str                     # Applied stipulation ID
    stipulation_version: str                # Applied stipulation version
    stipulation_hash: str                   # Hash of applied stipulation

    # Exposure tracking
    proxy_enforced: bool = True             # Whether proxy enforcement is active
    exposed_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))  # When contract was exposed
    exposed_by: Optional[str] = None        # Service/user that exposed the contract

    # Governance information
    audit_note: str = "Contract governed by stipulations"  # Audit note
    compliance_status: str = "compliant"    # Compliance status
    governance_version: str = "1.0.0"       # Version of governance framework

    # Tenant and scope information
    tenant_scope: Optional[str] = None      # Tenant scope if applicable
    access_level: str = "public"            # Access level (public, internal, partner)

    # Additional metadata
    custom_metadata: Dict[str, Any] = field(default_factory=dict)  # Custom audit metadata

    def __post_init__(self):
        """Validate audit metadata after initialization."""
        self._validate_metadata()

    def _validate_metadata(self) -> None:
        """Validate that audit metadata is properly formed."""
        errors = []

        required_fields = [
            "capability_category", "api_major_version", "contract_version",
            "stipulation_id", "stipulation_version", "stipulation_hash"
        ]

        for field in required_fields:
            if not getattr(self, field):
                errors.append(f"{field} is required")

        if self.compliance_status not in ["compliant", "non-compliant", "pending"]:
            errors.append("compliance_status must be one of: compliant, non-compliant, pending")

        if self.access_level not in ["public", "internal", "partner"]:
            errors.append("access_level must be one of: public, internal, partner")

        if errors:
            raise ValueError(f"Audit metadata validation failed: {'; '.join(errors)}")

    def to_dict(self) -> Dict[str, Any]:
        """Convert audit metadata to dictionary for injection into contracts."""
        return {
            "capability_category": self.capability_category,
            "api_major_version": self.api_major_version,
            "contract_version": self.contract_version,
            "stipulation_id": self.stipulation_id,
            "stipulation_version": self.stipulation_version,
            "stipulation_hash": self.stipulation_hash,
            "proxy_enforced": self.proxy_enforced,
            "exposed_at": self.exposed_at.isoformat(),
            "exposed_by": self.exposed_by,
            "audit_note": self.audit_note,
            "compliance_status": self.compliance_status,
            "governance_version": self.governance_version,
            "tenant_scope": self.tenant_scope,
            "access_level": self.access_level,
            **self.custom_metadata
        }

    def add_custom_metadata(self, key: str, value: Any) -> None:
        """Add custom metadata to the audit block."""
        self.custom_metadata[key] = value

    def get_audit_hash(self) -> str:
        """Generate a hash of the audit metadata for integrity verification."""
        audit_dict = self.to_dict()
        # Remove timestamp fields for consistent hashing
        audit_dict.pop('exposed_at', None)

        audit_json = json.dumps(audit_dict, sort_keys=True, separators=(',', ':'))
        return hashlib.sha256(audit_json.encode()).hexdigest()
