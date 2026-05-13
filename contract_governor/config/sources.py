"""
Concrete implementations of configuration sources for different backends.

This module provides implementations for file-based, S3, and DynamoDB configuration
storage, following the ConfigurationSource interface.
"""

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from ..core.models import StipulationConfig
from ..interfaces.configuration_source import ConfigurationSource
from .field_validator import (
    ParseResult,
    filter_unknown_fields,
    format_unknown_fields_warning,
    get_valid_stipulation_fields,
)

logger = logging.getLogger(__name__)


class LocalFileConfigSource(ConfigurationSource):
    """
    File-based configuration source for local development and testing.

    Supports both YAML and JSON formats with automatic format detection.
    """

    def __init__(self, config_dir: str = "config/stipulations"):
        """
        Initialize file-based configuration source.

        Args:
            config_dir: Directory containing configuration files
        """
        self.config_dir = Path(config_dir)
        self.config_dir.mkdir(parents=True, exist_ok=True)
        self._cache: dict[str, StipulationConfig] = {}
        self._last_modified: dict[str, float] = {}
        self._parse_results: Dict[str, ParseResult] = {}  # Track parse results by category:api_major

    def load_stipulations(self) -> Dict[str, StipulationConfig]:
        """Load all stipulation configurations from files."""
        stipulations = {}

        for file_path in self.config_dir.glob("*.yaml"):
            try:
                category, api_major = self._parse_filename(file_path.stem)
                key = f"{category}:{api_major}"
                parse_result = self._load_file(file_path)
                self._parse_results[key] = parse_result  # Store for later error message enhancement
                if parse_result.success and parse_result.config:
                    stipulations[key] = parse_result.config
            except Exception as e:
                logger.error(f"Failed to load stipulation from {file_path}: {e}")

        for file_path in self.config_dir.glob("*.json"):
            try:
                category, api_major = self._parse_filename(file_path.stem)
                key = f"{category}:{api_major}"
                if key not in stipulations:  # YAML takes precedence
                    parse_result = self._load_file(file_path)
                    self._parse_results[key] = parse_result  # Store for later error message enhancement
                    if parse_result.success and parse_result.config:
                        stipulations[key] = parse_result.config
            except Exception as e:
                logger.error(f"Failed to load stipulation from {file_path}: {e}")

        return stipulations

    def load_stipulation(self, category: str, api_major_version: str) -> Optional[StipulationConfig]:
        """
        Load a specific stipulation configuration.

        Args:
            category: API category name
            api_major_version: API major version string

        Returns:
            StipulationConfig if successfully loaded, None otherwise

        Requirements: 2.1, 2.2, 2.3
        """
        filename_base = f"{category}_{api_major_version}"
        key = f"{category}:{api_major_version}"

        # Try YAML first, then JSON
        for ext in [".yaml", ".json"]:
            file_path = self.config_dir / f"{filename_base}{ext}"
            if file_path.exists():
                parse_result = self._load_file(file_path)
                self._parse_results[key] = parse_result  # Store for later error message enhancement
                return parse_result.config if parse_result.success else None

        # No file found - store a ParseResult indicating file not found
        self._parse_results[key] = ParseResult(
            success=False,
            source_path=str(self.config_dir / f"{filename_base}.yaml"),
            source_exists=False,
            error_message=f"No stipulation file found for {key}"
        )
        return None

    def get_parse_result(self, category: str, api_major_version: str) -> Optional[ParseResult]:
        """
        Get the parse result for a specific stipulation.

        This allows callers to get detailed information about why a stipulation
        failed to load (e.g., file not found vs parse error).

        Args:
            category: API category name
            api_major_version: API major version string

        Returns:
            ParseResult if available, None otherwise
        """
        key = f"{category}:{api_major_version}"
        return self._parse_results.get(key)

    def save_stipulation(self, category: str, api_major_version: str, config: StipulationConfig) -> None:
        """Save a stipulation configuration to YAML file."""
        filename = f"{category}_{api_major_version}.yaml"
        file_path = self.config_dir / filename

        config_dict = {
            "stipulation_id": config.stipulation_id,
            "stipulation_version": config.stipulation_version,
            "exposure_policy": config.exposure_policy,
            "proxy_prefix_format": config.proxy_prefix_format,
            "requires_scope_parameter": config.requires_scope_parameter,
            "forbid_methods": config.forbid_methods,
            "required_fields": config.required_fields,
            "require_openapi_major": config.require_openapi_major,
            "inject_metadata": config.inject_metadata,
            "metadata_block": config.metadata_block,
            "catalog_default_visible": config.catalog_default_visible,
            "extension_namespace": config.extension_namespace,
            "enforce_version_alignment": config.enforce_version_alignment
        }

        with open(file_path, 'w') as f:
            yaml.dump(config_dict, f, default_flow_style=False, sort_keys=True)

        logger.info(f"Saved stipulation {category}:{api_major_version} to {file_path}")

    def delete_stipulation(self, category: str, api_major_version: str) -> bool:
        """Delete a stipulation configuration file."""
        filename_base = f"{category}_{api_major_version}"
        deleted = False

        for ext in [".yaml", ".json"]:
            file_path = self.config_dir / f"{filename_base}{ext}"
            if file_path.exists():
                file_path.unlink()
                deleted = True
                logger.info(f"Deleted stipulation file {file_path}")

        return deleted

    def list_categories(self) -> List[str]:
        """List all available API categories."""
        categories = set()

        for file_path in self.config_dir.glob("*.yaml"):
            try:
                category, _ = self._parse_filename(file_path.stem)
                categories.add(category)
            except ValueError:
                continue

        for file_path in self.config_dir.glob("*.json"):
            try:
                category, _ = self._parse_filename(file_path.stem)
                categories.add(category)
            except ValueError:
                continue

        return sorted(list(categories))

    def list_versions(self, category: str) -> List[str]:
        """List all available API major versions for a category."""
        versions = set()

        for file_path in self.config_dir.glob(f"{category}_*.yaml"):
            try:
                _, api_major = self._parse_filename(file_path.stem)
                versions.add(api_major)
            except ValueError:
                continue

        for file_path in self.config_dir.glob(f"{category}_*.json"):
            try:
                _, api_major = self._parse_filename(file_path.stem)
                versions.add(api_major)
            except ValueError:
                continue

        return sorted(list(versions))

    def is_available(self) -> bool:
        """Check if the configuration directory is accessible."""
        return self.config_dir.exists() and os.access(self.config_dir, os.R_OK)

    def get_source_info(self) -> Dict[str, Any]:
        """Get information about the file-based configuration source."""
        return {
            "type": "local_file",
            "location": str(self.config_dir.absolute()),
            "available": self.is_available(),
            "file_count": len(list(self.config_dir.glob("*.yaml")) + list(self.config_dir.glob("*.json"))),
            "last_checked": datetime.now(timezone.utc).isoformat()
        }

    def _parse_filename(self, filename: str) -> tuple[str, str]:
        """Parse category and API major version from filename."""
        parts = filename.split('_')
        if len(parts) < 2:
            raise ValueError(f"Invalid filename format: {filename}")

        # Last part is API major version, everything else is category
        api_major = parts[-1]
        category = '_'.join(parts[:-1])

        return category, api_major

    def _load_file(self, file_path: Path) -> ParseResult:
        """
        Load configuration from a file with detailed result tracking.

        Args:
            file_path: Path to the configuration file

        Returns:
            ParseResult with detailed information about the parsing outcome

        Requirements: 1.1, 1.2, 1.3, 2.1, 2.2, 2.3
        """
        valid_fields = get_valid_stipulation_fields()

        if not file_path.exists():
            return ParseResult(
                success=False,
                source_path=str(file_path),
                source_exists=False,
                valid_fields=valid_fields,
                error_message=f"File not found: {file_path}"
            )

        try:
            with open(file_path, 'r') as f:
                if file_path.suffix == '.yaml':
                    data = yaml.safe_load(f)
                else:
                    data = json.load(f)

            # Use shared utility for field filtering
            filtered_data, unknown_fields = filter_unknown_fields(data)

            # Log warning for unknown fields using shared formatter
            if unknown_fields:
                logger.warning(format_unknown_fields_warning(
                    str(file_path), unknown_fields, valid_fields
                ))

            config = StipulationConfig(**filtered_data)

            return ParseResult(
                success=True,
                config=config,
                source_path=str(file_path),
                source_exists=True,
                unknown_fields=unknown_fields,
                valid_fields=valid_fields
            )

        except Exception as e:
            logger.error(f"Failed to parse stipulation from {file_path}: {e}", exc_info=True)
            return ParseResult(
                success=False,
                source_path=str(file_path),
                source_exists=True,
                valid_fields=valid_fields,
                error_message=str(e)
            )


class S3ConfigSource(ConfigurationSource):
    """
    S3-based configuration source for cloud deployments.

    Stores configurations as JSON objects in S3 with hierarchical key structure.
    """

    def __init__(self, bucket_name: str, prefix: str = "stipulations/", region: str = "us-east-1"):
        """
        Initialize S3-based configuration source.

        Args:
            bucket_name: S3 bucket name
            prefix: Key prefix for stipulation objects
            region: AWS region
        """
        self.bucket_name = bucket_name
        self.prefix = prefix.rstrip('/') + '/'
        self.region = region
        self._s3_client = None
        self._cache: dict[str, StipulationConfig] = {}
        self._cache_ttl = 300  # 5 minutes
        self._last_cache_time = 0
        self._parse_results: Dict[str, ParseResult] = {}  # Track parse results by category:api_major

    @property
    def s3_client(self):
        """Lazy initialization of S3 client."""
        if self._s3_client is None:
            try:
                import boto3
                self._s3_client = boto3.client('s3', region_name=self.region)
            except ImportError:
                raise ImportError("boto3 is required for S3ConfigSource. Install with: pip install boto3")
        return self._s3_client

    def load_stipulations(self) -> Dict[str, StipulationConfig]:
        """Load all stipulation configurations from S3."""
        stipulations = {}

        try:
            response = self.s3_client.list_objects_v2(
                Bucket=self.bucket_name,
                Prefix=self.prefix
            )

            for obj in response.get('Contents', []):
                key = obj['Key']
                if key.endswith('.json'):
                    try:
                        category, api_major = self._parse_s3_key(key)
                        result_key = f"{category}:{api_major}"
                        parse_result = self._load_s3_object(key)
                        self._parse_results[result_key] = parse_result
                        if parse_result.success and parse_result.config:
                            stipulations[result_key] = parse_result.config
                    except Exception as e:
                        logger.error(f"Failed to load stipulation from S3 key {key}: {e}")

        except Exception as e:
            logger.error(f"Failed to list S3 objects: {e}")

        return stipulations

    def load_stipulation(self, category: str, api_major_version: str) -> Optional[StipulationConfig]:
        """
        Load a specific stipulation configuration from S3.

        Args:
            category: API category name
            api_major_version: API major version string

        Returns:
            StipulationConfig if successfully loaded, None otherwise

        Requirements: 4.1, 4.2, 4.3
        """
        s3_key = f"{self.prefix}{category}/{api_major_version}.json"
        result_key = f"{category}:{api_major_version}"
        parse_result = self._load_s3_object(s3_key)
        self._parse_results[result_key] = parse_result
        return parse_result.config if parse_result.success else None

    def get_parse_result(self, category: str, api_major_version: str) -> Optional[ParseResult]:
        """
        Get the parse result for a specific stipulation.

        This allows callers to get detailed information about why a stipulation
        failed to load (e.g., S3 object not found vs parse error).

        Args:
            category: API category name
            api_major_version: API major version string

        Returns:
            ParseResult if available, None otherwise
        """
        key = f"{category}:{api_major_version}"
        return self._parse_results.get(key)

    def save_stipulation(self, category: str, api_major_version: str, config: StipulationConfig) -> None:
        """Save a stipulation configuration to S3."""
        key = f"{self.prefix}{category}/{api_major_version}.json"

        config_dict = {
            "stipulation_id": config.stipulation_id,
            "stipulation_version": config.stipulation_version,
            "exposure_policy": config.exposure_policy,
            "proxy_prefix_format": config.proxy_prefix_format,
            "requires_scope_parameter": config.requires_scope_parameter,
            "forbid_methods": config.forbid_methods,
            "required_fields": config.required_fields,
            "require_openapi_major": config.require_openapi_major,
            "inject_metadata": config.inject_metadata,
            "metadata_block": config.metadata_block,
            "catalog_default_visible": config.catalog_default_visible,
            "extension_namespace": config.extension_namespace,
            "enforce_version_alignment": config.enforce_version_alignment,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "source": "s3"
        }

        try:
            self.s3_client.put_object(
                Bucket=self.bucket_name,
                Key=key,
                Body=json.dumps(config_dict, indent=2),
                ContentType='application/json'
            )
            logger.info(f"Saved stipulation {category}:{api_major_version} to S3 key {key}")
        except Exception as e:
            logger.error(f"Failed to save stipulation to S3: {e}")
            raise

    def delete_stipulation(self, category: str, api_major_version: str) -> bool:
        """Delete a stipulation configuration from S3."""
        key = f"{self.prefix}{category}/{api_major_version}.json"

        try:
            self.s3_client.delete_object(Bucket=self.bucket_name, Key=key)
            logger.info(f"Deleted stipulation from S3 key {key}")
            return True
        except Exception as e:
            logger.error(f"Failed to delete stipulation from S3: {e}")
            return False

    def list_categories(self) -> List[str]:
        """List all available API categories from S3."""
        categories = set()

        try:
            response = self.s3_client.list_objects_v2(
                Bucket=self.bucket_name,
                Prefix=self.prefix,
                Delimiter='/'
            )

            for prefix_info in response.get('CommonPrefixes', []):
                prefix_key = prefix_info['Prefix']
                category = prefix_key[len(self.prefix):].rstrip('/')
                if category:
                    categories.add(category)

        except Exception as e:
            logger.error(f"Failed to list categories from S3: {e}")

        return sorted(list(categories))

    def list_versions(self, category: str) -> List[str]:
        """List all available API major versions for a category from S3."""
        versions = set()
        prefix = f"{self.prefix}{category}/"

        try:
            response = self.s3_client.list_objects_v2(
                Bucket=self.bucket_name,
                Prefix=prefix
            )

            for obj in response.get('Contents', []):
                key = obj['Key']
                if key.endswith('.json'):
                    filename = key[len(prefix):]
                    version = filename.replace('.json', '')
                    versions.add(version)

        except Exception as e:
            logger.error(f"Failed to list versions for {category} from S3: {e}")

        return sorted(list(versions))

    def is_available(self) -> bool:
        """Check if S3 bucket is accessible."""
        try:
            self.s3_client.head_bucket(Bucket=self.bucket_name)
            return True
        except Exception:
            return False

    def get_source_info(self) -> Dict[str, Any]:
        """Get information about the S3 configuration source."""
        return {
            "type": "s3",
            "bucket": self.bucket_name,
            "prefix": self.prefix,
            "region": self.region,
            "available": self.is_available(),
            "last_checked": datetime.now(timezone.utc).isoformat()
        }

    def _parse_s3_key(self, key: str) -> tuple[str, str]:
        """Parse category and API major version from S3 key."""
        relative_key = key[len(self.prefix):]
        parts = relative_key.split('/')

        if len(parts) != 2 or not parts[1].endswith('.json'):
            raise ValueError(f"Invalid S3 key format: {key}")

        category = parts[0]
        api_major = parts[1].replace('.json', '')

        return category, api_major

    def _load_s3_object(self, key: str) -> ParseResult:
        """
        Load configuration from S3 object with detailed result tracking.

        Args:
            key: S3 object key

        Returns:
            ParseResult with detailed information about the parsing outcome

        Requirements: 4.1, 4.2, 4.3
        """
        valid_fields = get_valid_stipulation_fields()

        try:
            response = self.s3_client.get_object(Bucket=self.bucket_name, Key=key)
            data = json.loads(response['Body'].read().decode('utf-8'))

            # Remove S3-specific metadata before field validation
            data.pop('created_at', None)
            data.pop('source', None)

            # Use shared utility for field filtering
            filtered_data, unknown_fields = filter_unknown_fields(data)

            # Log warning for unknown fields using shared formatter
            if unknown_fields:
                logger.warning(format_unknown_fields_warning(
                    key, unknown_fields, valid_fields
                ))

            config = StipulationConfig(**filtered_data)

            return ParseResult(
                success=True,
                config=config,
                source_path=key,
                source_exists=True,
                unknown_fields=unknown_fields,
                valid_fields=valid_fields
            )

        except self.s3_client.exceptions.NoSuchKey:
            # S3 object does not exist - not an error, just not found
            return ParseResult(
                success=False,
                source_path=key,
                source_exists=False,
                valid_fields=valid_fields,
                error_message=f"S3 object not found: {key}"
            )

        except Exception as e:
            # Check if it's a ClientError for NoSuchKey (alternative exception path)
            error_response = getattr(getattr(e, 'response', {}), 'get', lambda _x, _y: None)('Error', {})
            error_code = error_response.get('Code', '') if error_response is not None else ''
            if error_code == 'NoSuchKey' or 'NoSuchKey' in str(e) or '404' in str(e):
                return ParseResult(
                    success=False,
                    source_path=key,
                    source_exists=False,
                    valid_fields=valid_fields,
                    error_message=f"S3 object not found: {key}"
                )

            logger.error(f"Failed to load configuration from S3 key {key}: {e}", exc_info=True)
            return ParseResult(
                success=False,
                source_path=key,
                source_exists=True,  # Assume exists if we got a different error
                valid_fields=valid_fields,
                error_message=str(e)
            )


class DynamoDBConfigSource(ConfigurationSource):
    """
    DynamoDB-based configuration source for scalable cloud deployments.

    Stores configurations in a DynamoDB table with composite key structure.
    """

    def __init__(self, table_name: str, region: str = "us-east-1"):
        """
        Initialize DynamoDB-based configuration source.

        Args:
            table_name: DynamoDB table name
            region: AWS region
        """
        self.table_name = table_name
        self.region = region
        self._dynamodb = None
        self._table = None
        self._parse_results: Dict[str, ParseResult] = {}  # Track parse results by category:api_major

    @property
    def dynamodb(self):
        """Lazy initialization of DynamoDB resource."""
        if self._dynamodb is None:
            try:
                import boto3
                self._dynamodb = boto3.resource('dynamodb', region_name=self.region)
            except ImportError:
                raise ImportError("boto3 is required for DynamoDBConfigSource. Install with: pip install boto3")
        return self._dynamodb

    @property
    def table(self):
        """Lazy initialization of DynamoDB table."""
        if self._table is None:
            self._table = self.dynamodb.Table(self.table_name)
        return self._table

    def load_stipulations(self) -> Dict[str, StipulationConfig]:
        """Load all stipulation configurations from DynamoDB."""
        stipulations = {}

        try:
            response = self.table.scan()

            for item in response.get('Items', []):
                try:
                    category = item['category']
                    api_major = item['api_major_version']
                    result_key = f"{category}:{api_major}"
                    parse_result = self._item_to_config(item, result_key)
                    self._parse_results[result_key] = parse_result
                    if parse_result.success and parse_result.config:
                        stipulations[result_key] = parse_result.config
                except Exception as e:
                    logger.error(f"Failed to parse DynamoDB item: {e}")

            # Handle pagination
            while 'LastEvaluatedKey' in response:
                response = self.table.scan(ExclusiveStartKey=response['LastEvaluatedKey'])
                for item in response.get('Items', []):
                    try:
                        category = item['category']
                        api_major = item['api_major_version']
                        result_key = f"{category}:{api_major}"
                        parse_result = self._item_to_config(item, result_key)
                        self._parse_results[result_key] = parse_result
                        if parse_result.success and parse_result.config:
                            stipulations[result_key] = parse_result.config
                    except Exception as e:
                        logger.error(f"Failed to parse DynamoDB item: {e}")

        except Exception as e:
            logger.error(f"Failed to scan DynamoDB table: {e}")

        return stipulations

    def load_stipulation(self, category: str, api_major_version: str) -> Optional[StipulationConfig]:
        """
        Load a specific stipulation configuration from DynamoDB.

        Args:
            category: API category name
            api_major_version: API major version string

        Returns:
            StipulationConfig if successfully loaded, None otherwise

        Requirements: 5.1, 5.2, 5.3
        """
        result_key = f"{category}:{api_major_version}"
        valid_fields = get_valid_stipulation_fields()

        try:
            response = self.table.get_item(
                Key={
                    'category': category,
                    'api_major_version': api_major_version
                }
            )

            item = response.get('Item')
            if item:
                parse_result = self._item_to_config(item, result_key)
                self._parse_results[result_key] = parse_result
                return parse_result.config if parse_result.success else None

            # Item not found - store a ParseResult indicating item not found
            self._parse_results[result_key] = ParseResult(
                success=False,
                source_path=result_key,
                source_exists=False,
                valid_fields=valid_fields,
                error_message=f"No DynamoDB item found for {result_key}"
            )
            return None

        except Exception as e:
            logger.error(f"Failed to load stipulation {result_key} from DynamoDB: {e}")
            self._parse_results[result_key] = ParseResult(
                success=False,
                source_path=result_key,
                source_exists=False,  # Can't determine if exists when exception occurs
                valid_fields=valid_fields,
                error_message=str(e)
            )
            return None

    def get_parse_result(self, category: str, api_major_version: str) -> Optional[ParseResult]:
        """
        Get the parse result for a specific stipulation.

        This allows callers to get detailed information about why a stipulation
        failed to load (e.g., DynamoDB item not found vs conversion error).

        Args:
            category: API category name
            api_major_version: API major version string

        Returns:
            ParseResult if available, None otherwise
        """
        key = f"{category}:{api_major_version}"
        return self._parse_results.get(key)

    def save_stipulation(self, category: str, api_major_version: str, config: StipulationConfig) -> None:
        """Save a stipulation configuration to DynamoDB."""
        item = {
            'category': category,
            'api_major_version': api_major_version,
            'stipulation_id': config.stipulation_id,
            'stipulation_version': config.stipulation_version,
            'exposure_policy': config.exposure_policy,
            'proxy_prefix_format': config.proxy_prefix_format,
            'requires_scope_parameter': config.requires_scope_parameter,
            'forbid_methods': config.forbid_methods,
            'required_fields': config.required_fields,
            'require_openapi_major': config.require_openapi_major,
            'inject_metadata': config.inject_metadata,
            'metadata_block': config.metadata_block,
            'catalog_default_visible': config.catalog_default_visible,
            'extension_namespace': config.extension_namespace,
            'enforce_version_alignment': config.enforce_version_alignment,
            'created_at': datetime.now(timezone.utc).isoformat(),
            'updated_at': datetime.now(timezone.utc).isoformat(),
            'source': 'dynamodb'
        }

        try:
            self.table.put_item(Item=item)
            logger.info(f"Saved stipulation {category}:{api_major_version} to DynamoDB")
        except Exception as e:
            logger.error(f"Failed to save stipulation to DynamoDB: {e}")
            raise

    def delete_stipulation(self, category: str, api_major_version: str) -> bool:
        """Delete a stipulation configuration from DynamoDB."""
        try:
            self.table.delete_item(
                Key={
                    'category': category,
                    'api_major_version': api_major_version
                }
            )
            logger.info(f"Deleted stipulation {category}:{api_major_version} from DynamoDB")
            return True
        except Exception as e:
            logger.error(f"Failed to delete stipulation from DynamoDB: {e}")
            return False

    def list_categories(self) -> List[str]:
        """List all available API categories from DynamoDB."""
        categories = set()

        try:
            response = self.table.scan(
                ProjectionExpression='category'
            )

            for item in response.get('Items', []):
                categories.add(item['category'])

            # Handle pagination
            while 'LastEvaluatedKey' in response:
                response = self.table.scan(
                    ProjectionExpression='category',
                    ExclusiveStartKey=response['LastEvaluatedKey']
                )
                for item in response.get('Items', []):
                    categories.add(item['category'])

        except Exception as e:
            logger.error(f"Failed to list categories from DynamoDB: {e}")

        return sorted(list(categories))

    def list_versions(self, category: str) -> List[str]:
        """List all available API major versions for a category from DynamoDB."""
        versions = set()

        try:
            response = self.table.query(
                KeyConditionExpression='category = :category',
                ExpressionAttributeValues={':category': category},
                ProjectionExpression='api_major_version'
            )

            for item in response.get('Items', []):
                versions.add(item['api_major_version'])

        except Exception as e:
            logger.error(f"Failed to list versions for {category} from DynamoDB: {e}")

        return sorted(list(versions))

    def is_available(self) -> bool:
        """Check if DynamoDB table is accessible."""
        try:
            self.table.table_status
            return True
        except Exception:
            return False

    def get_source_info(self) -> Dict[str, Any]:
        """Get information about the DynamoDB configuration source."""
        info = {
            "type": "dynamodb",
            "table_name": self.table_name,
            "region": self.region,
            "available": False,
            "last_checked": datetime.now(timezone.utc).isoformat()
        }

        try:
            table_info = self.table.table_status
            info["available"] = True
            info["table_status"] = table_info
        except Exception as e:
            info["error"] = str(e)

        return info

    def _item_to_config(self, item: Dict[str, Any], source_key: str = "") -> ParseResult:
        """
        Convert DynamoDB item to StipulationConfig with detailed result tracking.

        Args:
            item: DynamoDB item dictionary
            source_key: DynamoDB key identifier for error messages (e.g., "category:api_major")

        Returns:
            ParseResult with detailed information about the conversion outcome

        Requirements: 5.1, 5.2, 5.3
        """
        valid_fields = get_valid_stipulation_fields()

        try:
            # Remove DynamoDB-specific fields before validation
            config_data = {k: v for k, v in item.items()
                          if k not in ['category', 'api_major_version', 'created_at', 'updated_at', 'source']}

            # Use shared utility for field filtering
            filtered_data, unknown_fields = filter_unknown_fields(config_data)

            # Log warning for unknown fields using shared formatter
            if unknown_fields:
                logger.warning(format_unknown_fields_warning(
                    source_key, unknown_fields, valid_fields
                ))

            config = StipulationConfig(**filtered_data)

            return ParseResult(
                success=True,
                config=config,
                source_path=source_key,
                source_exists=True,
                unknown_fields=unknown_fields,
                valid_fields=valid_fields
            )

        except Exception as e:
            logger.error(f"Failed to convert DynamoDB item to StipulationConfig: {e}", exc_info=True)
            return ParseResult(
                success=False,
                source_path=source_key,
                source_exists=True,
                valid_fields=valid_fields,
                error_message=str(e)
            )
