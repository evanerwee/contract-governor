"""
Contract Governor - Central orchestrator for contract validation, transformation, and exposure.

This module implements the core orchestration logic that ensures only validated,
transformed, and audit-stamped contracts are exposed to clients. It enforces
the strict separation between raw backend contracts and exposed client contracts.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, cast

from ..config.field_validator import ParseResult
from ..interfaces.contract_registry import ContractRegistry
from ..transformation.pipeline import TransformationPipeline
from ..validation.pipeline import ValidationPipeline
from .errors import (
    ContractNotFoundError,
    RegistryError,
    StipulationNotFoundError,
    StipulationParseError,
    StipulationViolationError,
    TransformationError,
    create_error_context,
)
from .models import (
    AuditMetadata,
    ExposedContractRecord,
    RawContractRecord,
    StipulationConfig,
    TransformContext,
    ValidationResult,
    VersionInfo,
)
from .monitoring import OperationType, get_global_audit_logger, monitor_performance
from .stipulation_processor import StipulationProcessor
from .template_models import ContractInstance


class ContractGovernor:
    """
    Central orchestrator for contract validation, transformation, and exposure.

    This class implements the core governance logic that ensures:
    1. Raw contracts from backend services are never exposed directly
    2. Only validated, transformed contracts are available to clients
    3. All exposed contracts include comprehensive audit metadata
    4. Stipulation policies are consistently enforced
    """

    def __init__(
        self,
        registry: ContractRegistry,
        stipulations: Dict[str, StipulationConfig],
        api_catalog: Optional[Dict[str, Any]] = None,
        implementation_registry: Optional[Any] = None,
        config_source: Optional[Any] = None,
    ):
        """
        Initialize the Contract Governor.

        Args:
            registry: Contract registry for storing raw and exposed contracts
            stipulations: Dictionary mapping category:api_major to stipulation configs
            api_catalog: Optional API catalog from control-plane with implementation mappings (DEPRECATED)
            implementation_registry: Implementation registry mapping operationIds to handlers (PROPER WAY)
            config_source: Optional configuration source for retrieving parse results
        """
        import logging

        logger = logging.getLogger(__name__)

        self.registry = registry
        self.stipulations = stipulations
        self.api_catalog = api_catalog or {}  # Keep for backward compatibility
        self.implementation_registry = implementation_registry
        self.config_source = config_source  # Store config source for parse result retrieval
        self._parse_results: Dict[str, ParseResult] = {}  # Track ParseResults by category:api_major
        self.stipulation_processor = StipulationProcessor(self)

        # Log initialization
        if self.implementation_registry:
            stats = self.implementation_registry.get_stats()
            logger.info("✅ ContractGovernor: Implementation Registry provided")
            logger.info(f"   📊 Total handlers: {stats['total_registered']}")
            logger.info(f"   📊 Categories: {len(stats['categories'])}")
            logger.info(f"   📋 Categories: {stats['categories']}")
            self.implementation_registry.log_summary()
        else:
            logger.warning("⚠️ ContractGovernor: NO Implementation Registry provided!")
            logger.warning("   Will fall back to deprecated catalog/discovery methods")

        # Log catalog (deprecated)
        if self.api_catalog:
            entries = self.api_catalog.get("entries", {})
            category_index = self.api_catalog.get("category_index", {})
            logger.info("📚 ContractGovernor: API Catalog provided (DEPRECATED)")
            logger.info(f"   📊 Entries: {len(entries)} implementations")
            logger.info(f"   📊 Category Index: {len(category_index)} categories")

    @monitor_performance(OperationType.CONTRACT_EXPOSURE)
    def ingest_backend_contract(
        self,
        contract: Dict[str, Any],
        category: str,
        api_major: str,
        source_service: str,
        contract_file_path: str,
        service_version: Optional[str] = None,
        environment: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> RawContractRecord:
        """
        Ingest a raw contract from a backend service - stores as RawContractRecord only.

        Raw contracts are NEVER exposed to clients and contain internal URLs
        and potentially unsafe methods.

        Args:
            contract: The OpenAPI specification dictionary
            category: API category (e.g., "evidence-query")
            api_major: API major version (e.g., "v1")
            source_service: Name of the service providing the contract
            contract_file_path: Original file path of the contract
            service_version: Optional version of the source service
            environment: Optional environment (dev, staging, prod)
            metadata: Optional additional metadata

        Returns:
            The stored raw contract record
        """
        # Extract version information from the contract
        version_info = self._extract_versions(contract, api_major)

        # Create raw contract record
        raw_record = RawContractRecord(
            category=category,
            api_major_version=api_major,
            contract_version=version_info.contract_version,
            source_service=source_service,
            raw_openapi_spec=contract,
            contract_file_path=contract_file_path,
            received_at=datetime.now(timezone.utc),
            service_version=service_version,
            environment=environment,
            metadata=metadata or {},
        )

        # Store the raw contract
        self.registry.store_raw_contract(raw_record)

        return raw_record

    @monitor_performance(OperationType.CONTRACT_EXPOSURE)
    def expose_contract(
        self,
        category: str,
        api_major: str,
        gateway_base_url: str,
        scope_parameters: Optional[Dict[str, str]] = None,
        target_audience: str = "public",
        metadata_overrides: Optional[Dict[str, Any]] = None,
    ) -> ExposedContractRecord:
        """
        Transform raw contract into exposed contract - the ONLY way contracts become public.

        This method validates the raw contract against stipulations, transforms it
        with proxy URLs and audit metadata, and creates an exposed contract record
        that is safe for client access.

        Args:
            category: API category
            api_major: API major version
            gateway_base_url: Base URL of the gateway service
            scope_parameters: Optional scope parameters (e.g., {"tenant_id": "acme"})
            target_audience: Target audience ("public", "internal", "partner")
            metadata_overrides: Optional metadata overrides

        Returns:
            The exposed contract record safe for client access

        Raises:
            ContractNotFoundError: If no raw contract exists for the category/api_major
            StipulationViolationError: If the contract violates stipulation requirements
        """
        # Create error context for this operation
        error_context = create_error_context(
            service_name="contract_stipulations",
            contract_category=category,
            api_major_version=api_major,
            operation="expose_contract",
        )

        # Get all raw contracts for this category:api_major
        all_raw_contracts = self.registry.list_raw_contracts()
        matching_contracts = [
            c for c in all_raw_contracts if c.category == category and c.api_major_version == api_major
        ]

        if not matching_contracts:
            raise ContractNotFoundError(
                category=category, api_major_version=api_major, contract_type="raw", context=error_context
            )

        # Use the first matching contract (or implement selection logic)
        raw_record = matching_contracts[0]

        # Get the stipulation configuration
        try:
            stipulation = self._get_stipulation(category, api_major)
        except Exception as e:
            raise RegistryError(
                message=f"Failed to get stipulation for {category}:{api_major}",
                error_code="STIPULATION_RETRIEVAL_FAILED",
                operation="get_stipulation",
                contract_key=f"{category}:{api_major}",
                context=error_context,
                cause=e,
            )

        # Validate the contract against the stipulation
        validation_result = self._validate_contract(raw_record.raw_openapi_spec, stipulation)
        if not validation_result.is_valid:
            error_context.stipulation_id = stipulation.stipulation_id
            raise StipulationViolationError(validation_result, context=error_context)

        # Create transformation context
        context = TransformContext(
            category=category,
            api_major_version=api_major,
            contract_version=raw_record.contract_version,
            gateway_base_url=gateway_base_url,
            scope_parameters=scope_parameters or {},
            target_audience=target_audience,
            metadata_overrides=metadata_overrides or {},
            source_service=raw_record.source_service,
            environment=raw_record.environment,
        )

        # Transform the contract
        try:
            transformed_spec = self._transform_contract(raw_record.raw_openapi_spec, stipulation, context)
        except Exception as e:
            raise TransformationError(
                message=f"Failed to transform contract {category}:{api_major}",
                error_code="CONTRACT_TRANSFORMATION_FAILED",
                transformation_stage="contract_transformation",
                original_contract=raw_record.raw_openapi_spec,
                context=error_context,
                cause=e,
            )

        # Create audit metadata
        try:
            audit_metadata = self._create_audit_metadata(stipulation, context, raw_record)
        except Exception as e:
            raise TransformationError(
                message=f"Failed to create audit metadata for {category}:{api_major}",
                error_code="AUDIT_METADATA_CREATION_FAILED",
                transformation_stage="audit_metadata_creation",
                context=error_context,
                cause=e,
            )

        # Build proxy prefix
        try:
            proxy_prefix = self._build_proxy_prefix(stipulation, context)
        except Exception as e:
            raise TransformationError(
                message=f"Failed to build proxy prefix for {category}:{api_major}",
                error_code="PROXY_PREFIX_BUILD_FAILED",
                transformation_stage="proxy_prefix_building",
                context=error_context,
                cause=e,
            )

        # Create exposed contract record
        exposed_record = ExposedContractRecord(
            category=category,
            api_major_version=api_major,
            contract_version=raw_record.contract_version,
            source_service=raw_record.source_service,
            exposed_openapi_spec=transformed_spec,
            openapi_mount_path=f"/contracts/{category}/{api_major}/openapi.json",
            proxy_prefix=proxy_prefix,
            stipulation_applied=stipulation.stipulation_id,
            stipulation_hash=stipulation.get_stipulation_hash(),
            exposed_at=datetime.now(timezone.utc),
            audit_metadata=audit_metadata.to_dict(),
            catalog_visible=stipulation.catalog_default_visible,
        )

        # Store the exposed contract
        self.registry.store_exposed_contract(exposed_record)

        # Log successful contract exposure for audit
        audit_logger = get_global_audit_logger()
        if audit_logger is not None:
            audit_logger.log_contract_exposure(
                contract_category=category,
                api_major_version=api_major,
                stipulation_id=stipulation.stipulation_id,
                success=True,
                request_id=error_context.request_id,
                metadata={
                    "source_service": raw_record.source_service,
                    "contract_version": raw_record.contract_version,
                    "proxy_prefix": proxy_prefix,
                    "target_audience": target_audience,
                },
            )

        return exposed_record

    def list_exposed_contracts(self, filters: Optional[Dict[str, Any]] = None) -> List[ExposedContractRecord]:
        """
        List all exposed contracts - ONLY source for client-facing catalog.

        Args:
            filters: Optional filtering criteria

        Returns:
            List of exposed contract records
        """
        return self.registry.list_exposed_contracts(filters)

    def list_raw_contracts(self, filters: Optional[Dict[str, Any]] = None) -> List[RawContractRecord]:
        """
        List all raw contracts for debugging and internal processing.

        Args:
            filters: Optional filtering criteria

        Returns:
            List of raw contract records
        """
        return self.registry.list_raw_contracts()

    def get_exposed_contract(self, category: str, api_major: str) -> Optional[ExposedContractRecord]:
        """
        Get specific exposed contract - ONLY source for client-facing specs.

        Args:
            category: API category
            api_major: API major version

        Returns:
            Exposed contract record if found, None otherwise
        """
        return self.registry.get_exposed_contract(category, api_major)

    def get_raw_contract(self, category: str, api_major: str) -> Optional[RawContractRecord]:
        """
        Get raw contract for internal processing only.

        This method should only be used for internal operations and debugging.
        Raw contracts should NEVER be exposed to clients.

        Args:
            category: API category
            api_major: API major version

        Returns:
            Raw contract record if found, None otherwise
        """
        return self.registry.get_raw_contract(category, api_major)

    def refresh_exposed_contract(
        self,
        category: str,
        api_major: str,
        gateway_base_url: str,
        scope_parameters: Optional[Dict[str, str]] = None,
        target_audience: str = "public",
        metadata_overrides: Optional[Dict[str, Any]] = None,
    ) -> Optional[ExposedContractRecord]:
        """
        Refresh an exposed contract by re-validating and re-transforming the raw contract.

        This is useful when stipulation policies change or when contracts need to be
        re-processed with updated parameters.

        Args:
            category: API category
            api_major: API major version
            gateway_base_url: Base URL of the gateway service
            scope_parameters: Optional scope parameters
            target_audience: Target audience
            metadata_overrides: Optional metadata overrides

        Returns:
            The refreshed exposed contract record, or None if no raw contract exists
        """
        # Check if raw contract exists
        if not self.registry.get_raw_contract(category, api_major):
            return None

        # Remove existing exposed contract
        self.registry.remove_exposed_contract(category, api_major)

        # Re-expose the contract
        # Safe: expose_contract always returns ExposedContractRecord; Any is due to untyped decorator
        return cast(
            ExposedContractRecord,
            self.expose_contract(
                category=category,
                api_major=api_major,
                gateway_base_url=gateway_base_url,
                scope_parameters=scope_parameters,
                target_audience=target_audience,
                metadata_overrides=metadata_overrides,
            ),
        )

    def get_governance_status(self, category: str, api_major: str) -> Dict[str, Any]:
        """
        Get comprehensive governance status for a contract.

        Args:
            category: API category
            api_major: API major version

        Returns:
            Dictionary with governance status information
        """
        raw_contract = self.registry.get_raw_contract(category, api_major)
        exposed_contract = self.registry.get_exposed_contract(category, api_major)

        # Try to get stipulation, handling new exception types
        try:
            stipulation = self._get_stipulation(category, api_major)
        except (StipulationNotFoundError, StipulationParseError):
            stipulation = None

        status = {
            "category": category,
            "api_major_version": api_major,
            "has_raw_contract": raw_contract is not None,
            "has_exposed_contract": exposed_contract is not None,
            "has_stipulation": stipulation is not None,
            "governance_complete": all([raw_contract, exposed_contract, stipulation]),
        }

        if raw_contract:
            status["raw_contract_info"] = {
                "source_service": raw_contract.source_service,
                "contract_version": raw_contract.contract_version,
                "received_at": raw_contract.received_at.isoformat(),
            }

        if exposed_contract:
            status["exposed_contract_info"] = {
                "stipulation_applied": exposed_contract.stipulation_applied,
                "exposed_at": exposed_contract.exposed_at.isoformat(),
                "catalog_visible": exposed_contract.catalog_visible,
                "proxy_prefix": exposed_contract.proxy_prefix,
            }

        if stipulation:
            status["stipulation_info"] = {
                "stipulation_id": stipulation.stipulation_id,
                "exposure_policy": stipulation.exposure_policy.value,
                "requires_scope_parameter": stipulation.requires_scope_parameter,
            }

        return status

    def expand_multi_tenant_contracts(self, category: str, api_major: str) -> List[ContractInstance]:
        """Expand multi-tenant contract templates into multiple instances."""
        return self.stipulation_processor.expand_contract_templates(category, api_major)

    def resolve_tenant_request(self, proxy_path: str) -> Optional[str]:
        """Resolve incoming tenant request to backend URL."""
        return self.stipulation_processor.get_backend_url_for_request(proxy_path)

    def _get_stipulation(self, category: str, api_major: str) -> StipulationConfig:
        """
        Get stipulation configuration for a category and API major version.

        Provides improved error messages that distinguish between missing files
        and parse failures.

        Args:
            category: API category name
            api_major: API major version string

        Returns:
            StipulationConfig for the specified category and version

        Raises:
            StipulationNotFoundError: If no stipulation file exists
            StipulationParseError: If stipulation file exists but failed to parse

        Requirements: 3.1, 3.2, 3.3, 3.4
        """
        key = f"{category}:{api_major}"
        stipulation = self.stipulations.get(key)

        if stipulation:
            return stipulation

        # Check if a stipulation file exists but failed to parse
        parse_info = self._get_stipulation_parse_info(category, api_major)

        if parse_info and parse_info.source_exists:
            # File exists but failed to parse or had issues
            if parse_info.error_message:
                raise StipulationParseError(
                    category=category,
                    api_major_version=api_major,
                    source_path=parse_info.source_path,
                    parse_error=parse_info.error_message,
                )
            elif parse_info.had_unknown_fields:
                raise StipulationParseError(
                    category=category,
                    api_major_version=api_major,
                    source_path=parse_info.source_path,
                    unknown_fields=parse_info.unknown_fields,
                )
            else:
                # File exists but no config was produced for unknown reason
                raise StipulationParseError(
                    category=category, api_major_version=api_major, source_path=parse_info.source_path
                )

        # No stipulation file exists
        raise StipulationNotFoundError(category=category, api_major_version=api_major)

    def _get_stipulation_parse_info(self, category: str, api_major: str) -> Optional[ParseResult]:
        """
        Get parse result information for a stipulation.

        This method retrieves detailed information about why a stipulation
        failed to load, enabling better error messages.

        Args:
            category: API category name
            api_major: API major version string

        Returns:
            ParseResult if available, None otherwise

        Requirements: 3.1
        """
        key = f"{category}:{api_major}"

        # First check local cache
        if key in self._parse_results:
            return self._parse_results[key]

        # Try to get from config source if available
        if self.config_source and hasattr(self.config_source, "get_parse_result"):
            parse_result = self.config_source.get_parse_result(category, api_major)
            if parse_result:
                self._parse_results[key] = parse_result
                # Safe: config_source.get_parse_result returns ParseResult; Any is due to untyped config_source
                return cast(ParseResult, parse_result)

        return None

    def store_parse_result(self, category: str, api_major: str, parse_result: ParseResult) -> None:
        """
        Store a parse result for later error message enhancement.

        This allows external code to provide parse results when loading
        stipulations, enabling better error messages in _get_stipulation().

        Args:
            category: API category name
            api_major: API major version string
            parse_result: The ParseResult to store
        """
        key = f"{category}:{api_major}"
        self._parse_results[key] = parse_result

    def get_stipulation_for_contract(self, category: str, api_major: str) -> Optional[StipulationConfig]:
        """Public method for StipulationProcessor to access stipulations."""
        try:
            return self._get_stipulation(category, api_major)
        except (StipulationNotFoundError, StipulationParseError):
            return None

    def get_implementation_from_catalog(self, category: str, api_major: str = "v1") -> Optional[Dict[str, str]]:
        """
        Get implementation details from API catalog.

        This is the PRIMARY source of truth for implementation paths.
        Uses category_index for O(1) direct lookup, falls back to string matching.

        Args:
            category: API category (e.g., "dataplane-registration", "authentication")
            api_major: API major version (default: "v1")

        Returns:
            Dictionary with module_path and class_name, or None if not found
        """
        import logging

        logger = logging.getLogger(__name__)

        if not self.api_catalog:
            logger.debug(f"No API catalog available for category: {category}")
            return None

        # PRIORITY 1: Use category_index for direct O(1) lookup (AUTHORITATIVE)
        category_index = self.api_catalog.get("category_index", {})
        logger.info(f"🔍 DEBUG: category_index has {len(category_index)} entries, looking for '{category}'")
        if len(category_index) > 0:
            logger.info(f"🔍 DEBUG: First 5 categories in index: {list(category_index.keys())[:5]}")
        if category in category_index:
            impl = category_index[category]
            logger.info(f"✅ Category index match! '{category}' → {impl['class_name']} (AUTHORITATIVE)")
            return {"module_path": impl["module_path"], "class_name": impl["class_name"]}

        # PRIORITY 2: Fallback to entries lookup with string manipulation (LEGACY)
        logger.debug(f"Category '{category}' not in category_index, trying entries lookup...")
        entries = self.api_catalog.get("entries", {})
        logger.debug(f"Catalog has {len(entries)} entries. Looking for category: {category}")

        # Extract the main part after last hyphen
        parts = category.split("-")
        main_part = parts[-1]

        # Build lookup keys with proper capitalization
        lookup_keys = [
            f"{main_part.title()}API",
            f"{category.title().replace('-', '')}API",
            f"{main_part.title()}Router",
            f"{category.title()}API",
            category,
        ]

        logger.debug(f"Trying lookup keys: {lookup_keys}")

        for key in lookup_keys:
            if key in entries:
                entry = entries[key]
                entry_category = entry.get("category", "").lower()
                logger.debug(
                    f"Found key '{key}' in catalog. Entry category: '{entry_category}', Looking for: '{category}'"
                )
                if (
                    entry_category == category.lower()
                    or main_part.lower() in entry_category
                    or entry_category in category.lower()
                ):
                    logger.info(f"✅ Catalog match! Category '{category}' → {entry['class_name']} (fallback)")
                    return {"module_path": entry["module_path"], "class_name": entry["class_name"]}
                else:
                    logger.debug(f"Key '{key}' found but category mismatch: '{entry_category}' vs '{category}'")

        logger.warning(f"❌ No catalog match for category: {category}")
        return None

    def _extract_versions(self, contract: Dict[str, Any], api_major: str) -> VersionInfo:
        """Extract version information from an OpenAPI contract."""
        openapi_version = contract.get("openapi", "")
        contract_version = contract.get("info", {}).get("version", "1.0.0")

        return VersionInfo(
            api_major_version=api_major, contract_version=contract_version, openapi_version=openapi_version
        )

    def _validate_contract(self, contract: Dict[str, Any], stipulation: StipulationConfig) -> ValidationResult:
        """Validate a contract against a stipulation."""
        pipeline = ValidationPipeline(stipulation)
        return pipeline.validate(contract)

    def _transform_contract(
        self, contract: Dict[str, Any], stipulation: StipulationConfig, context: TransformContext
    ) -> Dict[str, Any]:
        """Transform a contract according to stipulation policies."""
        pipeline = TransformationPipeline(stipulation)
        return pipeline.transform(contract, context)

    def _create_audit_metadata(
        self, stipulation: StipulationConfig, context: TransformContext, raw_record: RawContractRecord
    ) -> AuditMetadata:
        """Create comprehensive audit metadata for governance tracking."""
        return AuditMetadata(
            capability_category=context.category,
            api_major_version=context.api_major_version,
            contract_version=context.contract_version,
            stipulation_id=stipulation.stipulation_id,
            stipulation_version=stipulation.stipulation_version,
            stipulation_hash=stipulation.get_stipulation_hash(),
            exposed_by=f"ContractGovernor-{context.source_service}",
            audit_note=stipulation.metadata_block.get("audit_note", "Contract governed by stipulations"),
            tenant_scope=context.scope_parameters.get("tenant_id"),
            access_level=context.target_audience,
            custom_metadata={
                **stipulation.metadata_block,
                **context.metadata_overrides,
                "source_service": raw_record.source_service,
                "environment": raw_record.environment,
                "original_file_path": raw_record.contract_file_path,
            },
        )

    def _build_proxy_prefix(self, stipulation: StipulationConfig, context: TransformContext) -> str:
        """Build the proxy URL prefix from stipulation configuration."""
        if hasattr(stipulation, "proxy_prefix_format") and stipulation.proxy_prefix_format:
            prefix = stipulation.proxy_prefix_format
            # Ensure prefix starts with '/' as required by validation
            return prefix if prefix.startswith("/") else f"/{prefix}"

        # Fallback to category/version format
        return f"/{context.category}/{context.api_major_version}"

    def _hash_stipulation(self, stipulation: StipulationConfig) -> str:
        """Generate a hash of the stipulation for non-repudiation tracking."""
        return stipulation.get_stipulation_hash()

    def get_processing_summary(self) -> Dict[str, Any]:
        """Get comprehensive processing summary with metadata for debugging."""
        raw_contracts = self.registry.list_raw_contracts()
        exposed_contracts = self.registry.list_exposed_contracts()

        # Group by category
        categories: Dict[str, Dict[str, list[Any]]] = {}
        for raw in raw_contracts:
            if raw.category not in categories:
                categories[raw.category] = {"raw": [], "exposed": []}
            categories[raw.category]["raw"].append(raw.get_processing_metadata())

        for exposed in exposed_contracts:
            if exposed.category not in categories:
                categories[exposed.category] = {"raw": [], "exposed": []}
            categories[exposed.category]["exposed"].append(exposed.get_processing_metadata())

        return {
            "total_raw_contracts": len(raw_contracts),
            "total_exposed_contracts": len(exposed_contracts),
            "total_stipulations": len(self.stipulations),
            "categories": categories,
            "stipulations": {
                key: {
                    "stipulation_id": stip.stipulation_id,
                    "exposure_policy": stip.exposure_policy,
                    "proxy_prefix_format": stip.proxy_prefix_format,
                    "requires_scope_parameter": stip.requires_scope_parameter,
                }
                for key, stip in self.stipulations.items()
            },
        }

    def get_contract_processing_details(self, category: str, api_major: str) -> Dict[str, Any]:
        """Get detailed processing information for a specific contract."""
        raw_contract = self.registry.get_raw_contract(category, api_major)
        exposed_contract = self.registry.get_exposed_contract(category, api_major)
        stipulation = (
            self._get_stipulation(category, api_major) if f"{category}:{api_major}" in self.stipulations else None
        )

        details = {
            "category": category,
            "api_major_version": api_major,
            "processing_status": {
                "has_raw": raw_contract is not None,
                "has_exposed": exposed_contract is not None,
                "has_stipulation": stipulation is not None,
                "fully_processed": all([raw_contract, exposed_contract, stipulation]),
            },
        }

        if raw_contract:
            details["raw_contract"] = raw_contract.get_processing_metadata()

        if exposed_contract:
            details["exposed_contract"] = exposed_contract.get_processing_metadata()

        if stipulation:
            details["stipulation"] = {
                "stipulation_id": stipulation.stipulation_id,
                "stipulation_version": stipulation.stipulation_version,
                "exposure_policy": stipulation.exposure_policy.value,
                "proxy_prefix_format": stipulation.proxy_prefix_format,
                "requires_scope_parameter": stipulation.requires_scope_parameter,
                "catalog_default_visible": stipulation.catalog_default_visible,
                "stipulation_hash": stipulation.get_stipulation_hash(),
            }

        return details
