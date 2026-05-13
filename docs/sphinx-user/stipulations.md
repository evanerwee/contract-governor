# Stipulation Authoring

## Stipulation File Format

Stipulations are YAML files that bind a governance policy to an OpenAPI contract.

```yaml
stipulation_id: registration-v1
stipulation_version: "1.0.0"
contract_path: registration/v1.0.0/registration_api.yaml
implementation_module: registration.api.endpoints
implementation_router_class: create_registration_router
exposure_policy: tenant-scoped
proxy_prefix_format: "/api/{scope_id}/registration/v1"
requires_scope_parameter: true
```

## Required Fields

| Field | Type | Description |
|-------|------|-------------|
| `stipulation_id` | string | Unique identifier for this stipulation |
| `stipulation_version` | string | Semantic version of the stipulation |
| `contract_path` | string | Path to the OpenAPI YAML relative to docs directory |
| `implementation_module` | string | Python module containing the route implementation |
| `implementation_router_class` | string | Factory function that returns a FastAPI router |
| `exposure_policy` | enum | One of: `global-data-plane`, `global-control-plane`, `tenant-scoped`, `admin-only` |
| `proxy_prefix_format` | string | URL template for the proxy prefix |

## Optional Fields

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `requires_scope_parameter` | bool | `false` | Whether the contract requires a scope parameter |
| `visible` | bool | `true` | Whether the contract appears in the catalog |

## Validation

Use the verification tool to check your stipulation:

```bash
python tools/verify_contract_governor_setup.py <service_name>
```

This checks that the stipulation, OpenAPI contract, and implementation module
are all consistent.
