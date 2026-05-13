"""
Template models for dynamic multi-tenancy contract expansion.

Enables contract-governor to generate multiple endpoint instances from
single contract templates based on discovered data-plane resources.
"""

import hashlib
import json
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, cast

from contract_governor.core.models import StipulationConfig


class VariableSource(str, Enum):
    """Sources for template variables."""
    DISCOVERY = "discovery"      # From data-plane discovery process
    STATIC = "static"           # Static configuration
    RUNTIME = "runtime"         # Runtime parameters (tenant_id, etc.)


@dataclass
class TemplateVariable:
    """Definition of a template variable."""
    name: str                           # Variable name (e.g., "tenant_id")
    source: VariableSource              # Where variable comes from
    values: List[str] = field(default_factory=list)  # Possible values
    default: Optional[str] = None       # Default value
    required: bool = True               # Whether variable is required
    pattern: Optional[str] = None       # Regex pattern for validation

    def __post_init__(self):
        """Validate variable definition."""
        if self.required and not self.values and not self.default:
            raise ValueError(f"Required variable {self.name} must have values or default")

        if self.pattern:
            try:
                re.compile(self.pattern)
            except re.error as e:
                raise ValueError(f"Invalid pattern for {self.name}: {e}")


@dataclass
class ContractTemplate:
    """Template for generating multiple contract instances."""
    template_id: str                    # Unique template identifier
    base_contract: Dict[str, Any]       # Base OpenAPI contract
    variables: Dict[str, TemplateVariable] = field(default_factory=dict)
    path_template: str = ""             # URL path template with variables
    backend_template: str = ""          # Backend URL template

    def __post_init__(self):
        """Validate template configuration."""
        if not self.template_id:
            raise ValueError("template_id is required")
        if not self.base_contract:
            raise ValueError("base_contract is required")

    def get_template_variables(self) -> List[str]:
        """Extract variable names from templates."""
        variables = set()

        # Extract from path template
        if self.path_template:
            variables.update(re.findall(r'\{(\w+)\}', self.path_template))

        # Extract from backend template
        if self.backend_template:
            variables.update(re.findall(r'\{(\w+)\}', self.backend_template))

        # Extract from contract paths
        for path in self.base_contract.get('paths', {}).keys():
            variables.update(re.findall(r'\{(\w+)\}', path))

        return list(variables)

    def validate_variables(self) -> List[str]:
        """Validate that all template variables are defined."""
        template_vars = set(self.get_template_variables())
        defined_vars = set(self.variables.keys())

        missing = template_vars - defined_vars
        return list(missing)


@dataclass
class ContractInstance:
    """Generated contract instance from template."""
    instance_id: str                    # Unique instance identifier
    template_id: str                    # Source template ID
    variable_values: Dict[str, str]     # Resolved variable values
    contract: Dict[str, Any]            # Generated OpenAPI contract
    proxy_path: str                     # Generated proxy path
    backend_url: str                    # Generated backend URL

    def get_resolution_key(self) -> str:
        """Generate key for resolving back to template."""
        # Create deterministic key from variable values
        sorted_vars = sorted(self.variable_values.items())
        var_str = "&".join(f"{k}={v}" for k, v in sorted_vars)
        return f"{self.template_id}?{var_str}"


@dataclass
class TemplateExpansionConfig:
    """Configuration for template expansion."""
    max_instances: int = 100            # Maximum instances per template
    variable_discovery_enabled: bool = True  # Enable variable discovery
    cache_instances: bool = True        # Cache generated instances
    validate_backends: bool = False     # Validate backend URLs exist

    def __post_init__(self):
        """Validate configuration."""
        if self.max_instances <= 0:
            raise ValueError("max_instances must be positive")


class TemplateExpander:
    """Expands contract templates into multiple instances."""

    def __init__(self, config: TemplateExpansionConfig | None = None):
        """Initialize expander with optional expansion configuration and instance caches."""
        self.config = config or TemplateExpansionConfig()
        self._instance_cache: Dict[str, ContractInstance] = {}
        self._resolution_map: Dict[str, str] = {}  # proxy_path -> instance_id

    def expand_template(self, template: ContractTemplate) -> List[ContractInstance]:
        """Expand template into multiple contract instances."""
        # Validate template
        missing_vars = template.validate_variables()
        if missing_vars:
            raise ValueError(f"Template {template.template_id} missing variables: {missing_vars}")

        instances = []

        # Generate all combinations of variable values
        combinations = self._generate_variable_combinations(template.variables)

        if len(combinations) > self.config.max_instances:
            raise ValueError(f"Template would generate {len(combinations)} instances, max is {self.config.max_instances}")

        for combo in combinations:
            instance = self._create_instance(template, combo)
            instances.append(instance)

            # Cache instance
            if self.config.cache_instances:
                self._instance_cache[instance.instance_id] = instance
                self._resolution_map[instance.proxy_path] = instance.instance_id

        return instances

    def resolve_request(self, proxy_path: str) -> Optional[ContractInstance]:
        """Resolve incoming request to contract instance."""
        # Direct lookup first
        if proxy_path in self._resolution_map:
            instance_id = self._resolution_map[proxy_path]
            return self._instance_cache.get(instance_id)

        # Pattern matching for dynamic paths
        for cached_path, instance_id in self._resolution_map.items():
            if self._paths_match(proxy_path, cached_path):
                return self._instance_cache.get(instance_id)

        return None

    def _generate_variable_combinations(self, variables: Dict[str, TemplateVariable]) -> List[Dict[str, str]]:
        """Generate all combinations of variable values."""
        if not variables:
            return [{}]

        combinations: List[Dict[str, str]] = [{}]

        for var_name, var_def in variables.items():
            new_combinations = []

            values = var_def.values or ([var_def.default] if var_def.default else [])
            if not values:
                raise ValueError(f"No values available for variable {var_name}")

            for combo in combinations:
                for value in values:
                    new_combo = combo.copy()
                    new_combo[var_name] = value
                    new_combinations.append(new_combo)

            combinations = new_combinations

        return combinations

    def _create_instance(self, template: ContractTemplate, variables: Dict[str, str]) -> ContractInstance:
        """Create contract instance from template and variables."""
        # Generate instance ID
        var_hash = hashlib.sha256(json.dumps(variables, sort_keys=True).encode()).hexdigest()[:8]
        instance_id = f"{template.template_id}-{var_hash}"

        # Substitute variables in contract
        contract = self._substitute_contract_variables(template.base_contract, variables)

        # Generate proxy path
        proxy_path = self._substitute_variables(template.path_template, variables)

        # Generate backend URL
        backend_url = self._substitute_variables(template.backend_template, variables)

        return ContractInstance(
            instance_id=instance_id,
            template_id=template.template_id,
            variable_values=variables,
            contract=contract,
            proxy_path=proxy_path,
            backend_url=backend_url
        )

    def _substitute_contract_variables(self, contract: Dict[str, Any], variables: Dict[str, str]) -> Dict[str, Any]:
        """Substitute variables in OpenAPI contract."""
        contract_str = json.dumps(contract)

        for var_name, value in variables.items():
            contract_str = contract_str.replace(f"{{{var_name}}}", value)

        # Safe: json.loads on a string produced by json.dumps always returns the same structure (dict)
        return cast(Dict[str, Any], json.loads(contract_str))

    def _substitute_variables(self, template: str, variables: Dict[str, str]) -> str:
        """Substitute variables in string template."""
        result = template
        for var_name, value in variables.items():
            result = result.replace(f"{{{var_name}}}", value)
        return result

    def _paths_match(self, request_path: str, template_path: str) -> bool:
        """Check if request path matches template path pattern."""
        # Convert template path to regex
        pattern = re.escape(template_path)
        pattern = pattern.replace(r'\{[^}]+\}', r'[^/]+')  # Replace variables with pattern
        pattern = f"^{pattern}$"

        return bool(re.match(pattern, request_path))


@dataclass
class DiscoverySource:
    """Configuration for data-plane discovery."""
    source_type: str                    # "s3", "api", "database"
    connection_config: Dict[str, Any]   # Connection configuration
    variable_mapping: Dict[str, str]    # Map discovery fields to variables
    refresh_interval: int = 300         # Refresh interval in seconds

    def __post_init__(self):
        """Validate discovery source."""
        if not self.source_type:
            raise ValueError("source_type is required")
        if not self.variable_mapping:
            raise ValueError("variable_mapping is required")


class VariableDiscovery:
    """Discovers variable values from data-plane sources."""

    def __init__(self):
        """Initialize variable discovery with empty source and value registries."""
        self._sources: Dict[str, DiscoverySource] = {}
        self._discovered_values: Dict[str, List[str]] = {}

    def add_source(self, name: str, source: DiscoverySource):
        """Add discovery source."""
        self._sources[name] = source

    def discover_variables(self, variable_names: List[str]) -> Dict[str, List[str]]:
        """Discover values for specified variables."""
        results = {}

        for var_name in variable_names:
            values = []

            # Check each source for this variable
            for source_name, source in self._sources.items():
                if var_name in source.variable_mapping.values():
                    discovered = self._discover_from_source(source, var_name)
                    values.extend(discovered)

            # Remove duplicates and store
            results[var_name] = list(set(values))

        return results

    def _discover_from_source(self, source: DiscoverySource, _variable_name: str) -> List[str]:
        """Discover values from specific source."""
        # This would be implemented based on source type
        # For now, return empty list
        return []


@dataclass
class MultiTenantStipulation:
    """Extended stipulation with multi-tenant template support."""
    base_stipulation: 'StipulationConfig'  # Base stipulation config
    template: Optional[ContractTemplate] = None  # Contract template
    expansion_config: TemplateExpansionConfig = field(default_factory=TemplateExpansionConfig)
    discovery_sources: List[DiscoverySource] = field(default_factory=list)

    def __post_init__(self):
        """Validate multi-tenant stipulation."""
        if not self.base_stipulation:
            raise ValueError("base_stipulation is required")

    def is_templated(self) -> bool:
        """Check if this stipulation uses templates."""
        return self.template is not None

    def requires_expansion(self) -> bool:
        """Check if this stipulation requires template expansion."""
        if self.template is None:
            return False
        return bool(self.template.variables)
