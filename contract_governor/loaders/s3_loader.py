"""
S3 contract source with recursive folder search.

This module implements the ContractSource interface for loading OpenAPI
contracts from an S3 bucket, supporting recursive prefix scanning and
automatic version detection via semver parsing.
"""

import json
import logging
from typing import Any, Dict, List, Optional

import semver
import yaml

from ..core.models import StipulationConfig
from ..interfaces.contract_source import ContractSource
from ..validation.openapi_validator import validate_openapi_spec

logger = logging.getLogger(__name__)


class S3ContractSource(ContractSource):
    """Load OpenAPI contracts from S3 with control-plane version structure."""

    def __init__(self, s3_client, bucket_name: str, control_plane_version: str,
                 contracts_prefix: str = "contracts", stipulations_prefix: str = "stipulations"):
        """Initialize S3 contract source with bucket, version, and prefix configuration."""
        self.s3_client_factory = s3_client
        self.bucket = bucket_name
        self.control_plane_major = self._extract_major_version(control_plane_version)
        self.contracts_prefix = contracts_prefix
        self.stipulations_prefix = stipulations_prefix

    def _get_s3_client(self):
        """Get fresh S3 client to avoid caching."""
        if callable(self.s3_client_factory):
            return self.s3_client_factory()
        return self.s3_client_factory

    def _extract_major_version(self, version: str) -> str:
        """Extract major version from semver (v1.1.0 -> v1)."""
        major = version.split('.')[0]
        if not major.startswith('v'):
            major = f'v{major}'
        return major

    def load_contracts(self) -> List[Dict[str, Any]]:
        """Load all OpenAPI contracts from S3 for control-plane major version.

        S3 Structure: {control_plane_major}/{contracts_prefix}/{category}/{version}/openapi.yaml
        Example: v1/contracts/evidence-query/v1/openapi.yaml

        Returns:
            List of contract metadata dicts ready for ingestion
        """
        contracts = []
        prefix = f"{self.control_plane_major}/{self.contracts_prefix}/"

        # Track validation stats
        total_files = 0
        valid_contracts = 0
        invalid_contracts = 0
        skipped_files = 0

        s3 = self._get_s3_client()
        paginator = s3.get_paginator('list_objects_v2')
        pages = paginator.paginate(Bucket=self.bucket, Prefix=prefix)

        logger.info(f"🔍 Loading contracts from s3://{self.bucket}/{prefix}")

        for page in pages:
            if 'Contents' not in page:
                continue

            for obj in page['Contents']:
                key = obj['Key']

                # Only process YAML/JSON files
                if not (key.endswith('.yaml') or key.endswith('.yml') or key.endswith('.json')):
                    skipped_files += 1
                    continue

                total_files += 1

                try:
                    contract_data = self._load_contract_from_key(key)
                    if contract_data:
                        contracts.append(contract_data)
                        valid_contracts += 1
                        logger.info(f"✅ Loaded contract: {key}")
                    else:
                        invalid_contracts += 1
                except Exception as e:
                    invalid_contracts += 1
                    logger.error(f"❌ Failed to load {key}: {e}")

        # Log summary
        logger.info("=" * 80)
        logger.info("📊 CONTRACT LOADING SUMMARY")
        logger.info("=" * 80)
        logger.info(f"  Total files scanned:     {total_files}")
        logger.info(f"  ✅ Valid contracts:      {valid_contracts}")
        logger.info(f"  ❌ Invalid contracts:    {invalid_contracts}")
        logger.info(f"  ⏭️  Skipped files:        {skipped_files}")
        logger.info(f"  Success rate:            {(valid_contracts/total_files*100) if total_files > 0 else 0:.1f}%")
        logger.info("=" * 80)

        if invalid_contracts > 0:
            logger.warning(f"⚠️  {invalid_contracts} contract(s) failed validation - check logs above for details")

        return contracts

    def _load_contract_from_key(self, key: str) -> Optional[Dict[str, Any]]:
        """Load single contract from S3 key.

        Expected path: {major}/{contracts_prefix}/{category}/{version}/openapi.yaml
        Example: v1/contracts/evidence-query/v1/openapi.yaml
        """
        s3 = self._get_s3_client()
        response = s3.get_object(Bucket=self.bucket, Key=key)
        content = response['Body'].read().decode('utf-8')

        if key.endswith('.json'):
            contract = json.loads(content)
        else:
            contract = yaml.safe_load(content)

        # Validate the contract before processing
        if not validate_openapi_spec(contract, key):
            logger.error(f"❌ Skipping invalid contract: {key}")
            return None

        # Parse: v1/contracts/evidence-query/v1/openapi.yaml
        parts = key.split('/')
        if len(parts) < 5:
            logger.warning(f"Invalid path structure: {key}")
            return None

        category = parts[2]  # evidence-query or authorization_0
        version_str = parts[3]  # v1.0.0
        filename = parts[4]  # contract_file.yaml

        # Extract base filename without extension for unique source service
        base_filename = filename.rsplit('.', 1)[0].replace('_api', '').replace('-api', '')

        # Normalize version to major version using semver
        try:
            # Remove 'v' prefix if present
            clean_version = version_str.lstrip('v')
            parsed = semver.VersionInfo.parse(clean_version)
            api_major = f"v{parsed.major}"
        except ValueError:
            # Fallback for non-semver versions
            api_major = version_str.split('.')[0]
            if not api_major.startswith('v'):
                api_major = f'v{api_major}'

        return {
            'contract': contract,
            'category': category,
            'api_major': api_major,
            'source_service': f"{base_filename}-service",
            'contract_file_path': f"s3://{self.bucket}/{key}",
            'service_version': contract.get('info', {}).get('version', '1.0.0')
        }

    def load_stipulations(self) -> Dict[str, StipulationConfig]:
        """Load all stipulations from S3 for control-plane major version.

        S3 Structure: {control_plane_major}/{stipulations_prefix}/{category}_{version}.yaml
        Example: v1/stipulations/evidence-query_v1.yaml

        Returns:
            Dict mapping "category:version" to StipulationConfig
        """
        stipulations = {}
        prefix = f"{self.control_plane_major}/{self.stipulations_prefix}/"

        s3 = self._get_s3_client()
        paginator = s3.get_paginator('list_objects_v2')
        pages = paginator.paginate(Bucket=self.bucket, Prefix=prefix)

        for page in pages:
            if 'Contents' not in page:
                continue

            for obj in page['Contents']:
                key = obj['Key']

                # Skip schema files and non-YAML/JSON files
                filename = key.split('/')[-1]
                if filename in ['schema.json', 'schema.yaml', 'schema.yml']:
                    continue

                if not (key.endswith('.yaml') or key.endswith('.yml') or key.endswith('.json')):
                    continue

                try:
                    stip_data = self._load_stipulation_from_key(key)
                    if stip_data:
                        category, version, config = stip_data
                        stipulations[f"{category}:{version}"] = config
                        logger.info(f"Loaded stipulation: {category}:{version}")
                except Exception as e:
                    logger.error(f"Failed to load stipulation {key}: {e}")

        return stipulations

    def _load_stipulation_from_key(self, key: str) -> Optional[tuple[str, str, StipulationConfig]]:
        """Load stipulation from S3 key.

        Expected: {major}/{stipulations_prefix}/category_version.yaml
        Example: v1/stipulations/evidence-query_v1.yaml
        """
        s3 = self._get_s3_client()
        response = s3.get_object(Bucket=self.bucket, Key=key)
        content = response['Body'].read().decode('utf-8')

        if key.endswith('.json'):
            data = json.loads(content)
        else:
            data = yaml.safe_load(content)

        # Parse filename: evidence-query_v1.yaml
        filename = key.split('/')[-1].rsplit('.', 1)[0]
        parts = filename.rsplit('_', 1)
        if len(parts) != 2:
            logger.warning(f"Invalid stipulation filename: {key}")
            return None

        category, version = parts
        config = StipulationConfig(**data)

        return category, version, config
