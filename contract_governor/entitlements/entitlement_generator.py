"""
Entitlement generator for creating SpiceDB manifests from OpenAPI contracts.

This module provides the EntitlementGenerator class which inspects OpenAPI
path operations and produces SpiceDB relationship tuples for fine-grained
authorization enforcement.
"""

import logging
from typing import Any, Dict, Optional, Set, cast

from .models import ActionType, EntitlementManifest, OperationEntitlement

logger = logging.getLogger(__name__)


class EntitlementGenerator:
    """
    Generates SpiceDB entitlement manifests from OpenAPI contracts.

    This class is responsible for:
    1. Parsing OpenAPI specifications
    2. Generating operation IDs from paths and methods
    3. Mapping HTTP verbs to SpiceDB actions
    4. Creating SpiceDB relationship tuples
    5. Tracking implementation status (real vs mock)
    """

    # HTTP methods we process
    SUPPORTED_METHODS = {'get', 'post', 'put', 'patch', 'delete'}

    # HTTP verb to action mapping
    VERB_TO_ACTION = {
        'get': ActionType.READ,
        'post': ActionType.WRITE,
        'put': ActionType.WRITE,
        'patch': ActionType.WRITE,
        'delete': ActionType.DELETE
    }

    def __init__(self):
        """Initialize the entitlement generator."""
        pass

    def generate_manifest(
        self,
        openapi_spec: Dict,
        implementation_registry: Optional[Dict[str, bool]] = None
    ) -> EntitlementManifest:
        """
        Generate contract manifest from OpenAPI specification.

        UPDATED: Removed dataplane_id and security_context_id - contracts are pure API definitions.
        Authorization relationships are created by control-plane during DataPlane registration.

        Args:
            openapi_spec: OpenAPI 3.x specification dictionary
            implementation_registry: Optional dict mapping operation_id -> is_implemented

        Returns:
            ContractManifest with all operations (no authorization relationships)

        Example:
            >>> generator = EntitlementGenerator()
            >>> manifest = generator.generate_manifest(
            ...     openapi_spec=spec,
            ...     implementation_registry={
            ...         "lexical-graph_prompts_status_get": True,
            ...         "lexical-graph_prompts_configure_post": False
            ...     }
            ... )
        """
        if implementation_registry is None:
            implementation_registry = {}

        # Extract contract metadata
        info = openapi_spec.get('info', {})
        contract_name = info.get('title', 'Unknown')
        contract_version = info.get('version', '0.0.0')

        # Create manifest (pure API definition)
        manifest = EntitlementManifest(
            contract_name=contract_name,
            contract_version=contract_version,
            operations=[],
            metadata={
                'openapi_version': openapi_spec.get('openapi', '3.0.0'),
                'servers': openapi_spec.get('servers', [])
            }
        )

        # Extract base path from servers[0].url if available
        base_path = self._extract_base_path(openapi_spec.get('servers', []))
        if base_path:
            logger.info(f"Using base path from servers: {base_path}")

        # Process all paths
        paths = openapi_spec.get('paths', {})
        for path, path_item in paths.items():
            operations = self._extract_operations_from_path(
                path=path,
                path_item=path_item,
                implementation_registry=implementation_registry,
                base_path=base_path,
                openapi_spec=openapi_spec
            )
            manifest.operations.extend(operations)

        logger.info(
            f"Generated entitlement manifest for {contract_name} v{contract_version}: "
            f"{len(manifest.operations)} operations, "
            f"{len(manifest.get_implemented_operations())} implemented, "
            f"{len(manifest.get_mock_operations())} mock"
        )

        return manifest

    def _extract_base_path(self, servers: list) -> str:
        """
        Extract base path from OpenAPI servers array.

        Extracts the path portion from servers[0].url if available.
        For example:
        - http://localhost:8040/api/hello/v1 -> /api/hello/v1
        - https://api.example.com/v2 -> /v2
        - http://localhost:8080 -> ""

        Args:
            servers: OpenAPI servers array

        Returns:
            Base path string (e.g., "/api/hello/v1") or empty string if none
        """
        if not servers or not isinstance(servers, list) or len(servers) == 0:
            return ""

        server_url = servers[0].get('url', '')
        if not server_url:
            return ""

        # Parse URL to extract path
        from urllib.parse import urlparse
        parsed = urlparse(server_url)
        # Safe cast: urlparse().path always returns str, but server_url is Any (from untyped dict)
        base_path: str = cast(str, parsed.path.rstrip('/'))  # Remove trailing slash

        return base_path

    def _extract_operations_from_path(
        self,
        path: str,
        path_item: Dict,
        implementation_registry: Dict[str, bool],
        base_path: str = "",
        openapi_spec: Dict[str, Any] | None = None
    ) -> list[OperationEntitlement]:
        """
        Extract all operations from a path item.

        Args:
            path: Relative path from OpenAPI paths section (e.g., "/greet")
            path_item: OpenAPI path item object
            implementation_registry: Dict mapping operation_id -> is_implemented
            base_path: Base path from servers[0].url (e.g., "/api/hello/v1")

        Returns:
            List of OperationEntitlement objects with full paths
        """
        operations = []

        # Construct full path by prepending base_path
        full_path = f"{base_path}{path}" if base_path else path

        for method in self.SUPPORTED_METHODS:
            if method not in path_item:
                continue

            operation_spec = path_item[method]

            # Use operationId from OpenAPI spec if available, otherwise generate
            operation_id = operation_spec.get('operationId')
            if operation_id:
                # Sanitize the operationId to match Pydantic pattern
                import re
                operation_id = re.sub(r'[^a-zA-Z0-9_-]', '', operation_id)
                operation_id = re.sub(r'[-_]+', '-', operation_id)
                operation_id = operation_id.strip('-')
            else:
                # Generate operation ID from path and method
                operation_id = self.generate_operation_id(path, method)

            # Generate snake_case version of operation_id
            operation_id_snake_case = self.generate_snake_case_operation_id(operation_id)

            # Extract path variables from the path
            path_variables = self.extract_path_variables(path)

            # Extract query parameters and metadata from the operation spec
            query_parameters, query_parameter_examples, query_parameter_required, query_parameter_types = self.extract_query_parameters(operation_spec)

            # Extract request body schema for POST/PUT
            request_body_schema = self.extract_request_body_schema(operation_spec) if method.upper() in ['POST', 'PUT', 'PATCH'] else None

            # Extract body parameters from request body schema
            body_parameters, body_parameter_examples, body_parameter_required, body_parameter_types = self.extract_body_parameters(request_body_schema, openapi_spec or {})

            # Determine action
            action = self.map_verb_to_action(method)

            # Check implementation status
            is_implemented = implementation_registry.get(operation_id, False)

            # Extract metadata
            tags = operation_spec.get('tags', [])
            summary = operation_spec.get('summary')
            description = operation_spec.get('description')
            deprecated = operation_spec.get('deprecated', False)

            # Generate control plane HTTPS URL
            cp_https = f"https://router/{operation_id_snake_case}"

            # Create operation entitlement (no relationships - those are created by control-plane)
            operation = OperationEntitlement(
                operation_id=operation_id,
                operation_id_snake_case=operation_id_snake_case,
                path=full_path,  # Use full path with base_path + relative path
                path_variables=path_variables,
                query_parameters=query_parameters,
                query_parameter_examples=query_parameter_examples,
                query_parameter_required=query_parameter_required,
                query_parameter_types=query_parameter_types,
                body_parameters=body_parameters,
                body_parameter_examples=body_parameter_examples,
                body_parameter_required=body_parameter_required,
                body_parameter_types=body_parameter_types,
                method=method.upper(),
                action=action,
                tags=tags,
                summary=summary,
                description=description,
                deprecated=deprecated,
                request_body_schema=request_body_schema,
                is_implemented=is_implemented,
                is_mock=not is_implemented,
                cp_https=cp_https
            )

            operations.append(operation)

            logger.debug(
                f"Extracted operation: {operation_id} (snake_case: {operation_id_snake_case}) "
                f"(action={action}, implemented={is_implemented}, path_vars={path_variables}, query_params={query_parameters})"
            )

        return operations

    @staticmethod
    def generate_operation_id(path: str, method: str) -> str:
        """
        Generate operation ID from path and method.

        Converts path to operation ID by:
        1. Removing leading slash
        2. Replacing path parameters {param} with sanitized versions
        3. Replacing remaining slashes with underscores
        4. Removing invalid characters to match Pydantic pattern ``^[a-zA-Z0-9_-]+$``
        5. Appending method in lowercase

        Args:
            path: API path (e.g., "/lexical-graph/prompts/provider/status")
            method: HTTP method (e.g., "get", "GET")

        Returns:
            Operation ID (e.g., "lexical-graph_prompts_provider_status_get")

        Examples:
            >>> EntitlementGenerator.generate_operation_id("/api/v1/users", "get")
            'api_v1_users_get'
            >>> EntitlementGenerator.generate_operation_id("/lexical-graph/prompts/status", "POST")
            'lexical-graph_prompts_status_post'
            >>> EntitlementGenerator.generate_operation_id("/users/{user_id}/posts", "GET")
            'users_user-id_posts_get'
        """
        import re

        # Remove leading slash
        clean_path = path.lstrip('/')

        # Replace path parameters {param} with param (remove curly braces)
        # e.g., /users/{user_id} -> /users/user_id
        clean_path = re.sub(r'\{([^}]+)\}', r'\1', clean_path)

        # Replace slashes with underscores
        clean_path = clean_path.replace('/', '_')

        # Remove any remaining invalid characters (keep only alphanumeric, underscore, dash)
        # This ensures compliance with Pydantic pattern: ^[a-zA-Z0-9_-]+$  # noqa
        clean_path = re.sub(r'[^a-zA-Z0-9_-]', '', clean_path)

        # Replace multiple underscores/dashes with single dash
        clean_path = re.sub(r'[-_]+', '-', clean_path)

        # Remove leading/trailing dashes
        clean_path = clean_path.strip('-')

        return f"{clean_path}_{method.lower()}"

    @staticmethod
    def generate_snake_case_operation_id(operation_id: str) -> str:
        """
        Generate snake_case version of operation_id for storage.

        Converts operation_id to lowercase snake_case by:
        1. Converting to lowercase
        2. Replacing dashes with underscores
        3. Ensuring valid snake_case format

        Args:
            operation_id: Original operation ID (e.g., "lexical-graph_prompts_status_get")

        Returns:
            Snake case operation ID (e.g., "lexical_graph_prompts_status_get")

        Examples:
            >>> EntitlementGenerator.generate_snake_case_operation_id("lexical-graph_prompts_status_get")
            'lexical_graph_prompts_status_get'
            >>> EntitlementGenerator.generate_snake_case_operation_id("api-v1-users-get")
            'api_v1_users_get'
        """
        import re

        # Convert to lowercase
        snake_case = operation_id.lower()

        # Replace dashes with underscores
        snake_case = snake_case.replace('-', '_')

        # Replace multiple underscores with single underscore
        snake_case = re.sub(r'_+', '_', snake_case)

        # Remove leading/trailing underscores
        snake_case = snake_case.strip('_')

        return snake_case

    @staticmethod
    def extract_path_variables(path: str) -> list[str]:
        """
        Extract path variables from OpenAPI path.

        Finds all variables in {variable} format and returns them as a list.

        Args:
            path: API path (e.g., "/users/{user_id}/posts/{post_id}")

        Returns:
            List of variable names (e.g., ["user_id", "post_id"])

        Examples:
            >>> EntitlementGenerator.extract_path_variables("/users/{user_id}/posts")
            ['user_id']
            >>> EntitlementGenerator.extract_path_variables("/api/v1/items/{item_id}/details/{detail_id}")
            ['item_id', 'detail_id']
            >>> EntitlementGenerator.extract_path_variables("/static/path")
            []
        """
        import re

        # Find all variables in {variable} format
        variables = re.findall(r'\{([^}]+)\}', path)

        return variables

    @staticmethod
    def extract_query_parameters(operation_spec: Dict) -> tuple[list[str], dict[str, str], dict[str, bool], dict[str, str]]:
        """
        Extract query parameter names, examples, required flags, and types from OpenAPI operation spec.

        Finds all parameters with 'in: query' and returns their metadata.

        Args:
            operation_spec: OpenAPI operation object (e.g., paths['/search'].get)

        Returns:
            Tuple of:
            - list of query parameter names
            - dict of param name to example value
            - dict of param name to required boolean
            - dict of param name to type string

        Examples:
            >>> spec = {"parameters": [{"name": "q", "in": "query", "required": true, "schema": {"type": "string"}, "example": "search term"}]}
            >>> EntitlementGenerator.extract_query_parameters(spec)
            (['q'], {'q': 'search term'}, {'q': True}, {'q': 'string'})
        """
        query_params = []
        query_param_examples = {}
        query_param_required = {}
        query_param_types = {}

        parameters = operation_spec.get('parameters', [])
        for param in parameters:
            if param.get('in') == 'query':
                param_name = param.get('name')
                if param_name:
                    query_params.append(param_name)

                    # Extract required flag (default False)
                    query_param_required[param_name] = param.get('required', False)

                    # Extract type from schema
                    schema = param.get('schema', {})
                    query_param_types[param_name] = schema.get('type', 'string')

                    # Extract example value if present
                    example = param.get('example')
                    if example is not None:
                        query_param_examples[param_name] = str(example)
                    elif schema.get('default') is not None:
                        # Fall back to schema default if no example
                        query_param_examples[param_name] = str(schema['default'])

        return query_params, query_param_examples, query_param_required, query_param_types

    @staticmethod
    def extract_request_body_schema(operation_spec: Dict) -> Optional[Dict[str, Any]]:
        """
        Extract request body schema from OpenAPI operation spec.

        Args:
            operation_spec: OpenAPI operation object

        Returns:
            Request body schema dict or None if no request body
        """
        request_body = operation_spec.get('requestBody', {})
        if not request_body:
            return None

        content = request_body.get('content', {})
        # Prefer application/json
        json_content = content.get('application/json', {})
        if json_content:
            # Safe cast: schema value from OpenAPI content is always a dict or None
            return cast(Optional[Dict[str, Any]], json_content.get('schema'))

        # Fall back to first content type
        for content_type, content_spec in content.items():
            # Safe cast: schema value from OpenAPI content is always a dict or None
            return cast(Optional[Dict[str, Any]], content_spec.get('schema'))

        return None

    @staticmethod
    def resolve_ref(schema: Dict, openapi_spec: Dict) -> Dict:
        """
        Resolve $ref references in a schema.

        Args:
            schema: Schema that may contain $ref
            openapi_spec: Full OpenAPI spec to resolve references from

        Returns:
            Resolved schema with $ref replaced by actual definition
        """
        if not isinstance(schema, dict):
            return schema

        if '$ref' in schema:
            ref_path = schema['$ref']
            # Parse reference path like "#/components/schemas/ExtractionSubmitRequest"
            if ref_path.startswith('#/'):
                parts = ref_path[2:].split('/')
                resolved = openapi_spec
                for part in parts:
                    resolved = resolved.get(part, {})
                return EntitlementGenerator.resolve_ref(resolved, openapi_spec)
            return schema

        return schema

    @staticmethod
    def extract_body_parameters(request_body_schema: Optional[Dict], openapi_spec: Dict) -> tuple[list[str], dict[str, Any], dict[str, bool], dict[str, str]]:
        """
        Extract body parameter names, examples, required flags, and types from request body schema.

        Args:
            request_body_schema: Request body schema from OpenAPI (may contain $ref)
            openapi_spec: Full OpenAPI spec for resolving $ref

        Returns:
            Tuple of:
            - list of body parameter names
            - dict of param name to example value
            - dict of param name to required boolean
            - dict of param name to type string
        """
        body_params: list[str] = []
        body_param_examples: dict[str, Any] = {}
        body_param_required: dict[str, bool] = {}
        body_param_types: dict[str, str] = {}

        if not request_body_schema:
            return body_params, body_param_examples, body_param_required, body_param_types

        # Resolve $ref if present
        resolved_schema = EntitlementGenerator.resolve_ref(request_body_schema, openapi_spec)

        if not resolved_schema or resolved_schema.get('type') != 'object':
            return body_params, body_param_examples, body_param_required, body_param_types

        properties = resolved_schema.get('properties', {})
        required_list = resolved_schema.get('required', [])

        for param_name, param_schema in properties.items():
            body_params.append(param_name)

            # Required flag
            body_param_required[param_name] = param_name in required_list

            # Type
            param_type = param_schema.get('type', 'string')
            if param_type == 'array':
                items_type = param_schema.get('items', {}).get('type', 'string')
                body_param_types[param_name] = f"array[{items_type}]"
            else:
                body_param_types[param_name] = param_type

            # Example value
            example = param_schema.get('example')
            if example is not None:
                body_param_examples[param_name] = example
            elif param_schema.get('default') is not None:
                body_param_examples[param_name] = param_schema['default']

        return body_params, body_param_examples, body_param_required, body_param_types

    @staticmethod
    def map_verb_to_action(method: str) -> ActionType:
        """
        Map HTTP verb to SpiceDB action type.

        Mapping:
        - GET -> read
        - POST, PUT, PATCH -> write
        - DELETE -> delete

        Args:
            method: HTTP method

        Returns:
            ActionType enum value
        """
        return EntitlementGenerator.VERB_TO_ACTION.get(
            method.lower(),
            ActionType.READ  # Default to read for unknown methods
        )

    def extract_operation_ids(self, openapi_spec: Dict) -> Set[str]:
        """
        Extract all operation IDs from an OpenAPI spec without generating full manifest.

        Useful for quick validation or comparison.

        Args:
            openapi_spec: OpenAPI specification dictionary

        Returns:
            Set of operation IDs
        """
        operation_ids = set()

        paths = openapi_spec.get('paths', {})
        for path, path_item in paths.items():
            for method in self.SUPPORTED_METHODS:
                if method in path_item:
                    operation_id = self.generate_operation_id(path, method)
                    operation_ids.add(operation_id)

        return operation_ids
