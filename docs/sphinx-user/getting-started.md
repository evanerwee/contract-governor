# Getting Started

## What is Contract Governor?

Contract Governor is a governance framework for OpenAPI contracts. It provides
validation, transformation, and controlled exposure of API specifications across
multi-tenant environments.

## Quick Start

### 1. Install

```bash
pip install contract-governor
```

### 2. Create a Stipulation

A stipulation defines how an OpenAPI contract should be governed — what gets
exposed, how URLs are transformed, and what validation rules apply.

```yaml
# config/stipulations/my-api_v1.yaml
stipulation_id: my-api-v1
stipulation_version: "1.0.0"
contract_path: my-api/v1.0.0/openapi.yaml
implementation_module: my_service.api.endpoints
implementation_router_class: create_router
exposure_policy: tenant-scoped
proxy_prefix_format: "/api/{tenant_id}/my-api/v1"
```

### 3. Mount in FastAPI

```python
from contract_governor.extensions import ContractGovernorFastAPIExtension

extension = ContractGovernorFastAPIExtension(app, config_dir="config/")
extension.load_stipulations()
```

## Next Steps

- [Concepts](concepts.md) — Understand stipulations, exposure policies, and contracts
- [Stipulation Authoring](stipulations.md) — Write your first stipulation
- [Deployment](deployment.md) — Deploy to ECS/EKS
