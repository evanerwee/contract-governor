# Usage Guide

Comprehensive guide to integrating `contract-governor` into your application.

## Table of Contents

- [Installation](#installation)
- [Core Concepts](#core-concepts)
- [Basic Usage](#basic-usage)
- [Stipulation Configuration](#stipulation-configuration)
- [FastAPI Integration](#fastapi-integration)
- [Multi-Tenant Setup](#multi-tenant-setup)
- [URL Rewriting](#url-rewriting)
- [Security Enforcement](#security-enforcement)
- [Audit Compliance](#audit-compliance)
- [Configuration Sources](#configuration-sources)
- [Deployment Patterns](#deployment-patterns)
- [Troubleshooting](#troubleshooting)

---

## Installation

### From PyPI

```bash
# Core package (validation + transformation only)
pip install contract-governor

# With FastAPI server support
pip install contract-governor[server]

# With deep OpenAPI validation (openapi-core)
pip install contract-governor[validation]

# With AWS config sources (S3, DynamoDB)
pip install contract-governor[aws]

# Everything
pip install contract-governor[all]
```

### Development Mode

```bash
# Clone and install in editable mode with all dev dependencies
git clone https://github.com/evanerwee/contract-governor.git
cd contract-governor
pip install -e ".[all]"
```

### Optional Extras Summary

| Extra | Packages Installed | Use Case |
|-------|-------------------|----------|
| *(core)* | pyyaml, httpx, pydantic, python-multipart, semver | Validation and transformation pipelines |
| `[server]` | fastapi, uvicorn | Serving governed contracts via HTTP |
| `[validation]` | openapi-core | Deep OpenAPI spec validation beyond structural checks |
| `[aws]` | boto3, botocore | Loading stipulations/contracts from S3 or DynamoDB |
| `[dev]` | pytest, hypothesis, ruff, mypy, sphinx, twine, build, etc. | Development, testing, documentation, publishing |
| `[all]` | All of the above | Convenience install for full functionality |

---

## Core Concepts

### Contracts

An OpenAPI specification (3.x) describing a backend service's API. Contracts are ingested from backend services and stored as **raw contracts** — internal representations that are never exposed directly to clients.

### Stipulations

Policy configurations that define how a contract should be validated, transformed, and exposed. A stipulation controls:

- Which HTTP methods are forbidden (e.g., DELETE, PATCH)
- How URLs are rewritten for proxy routing
- Whether tenant scoping is required
- What governance metadata is injected
- Catalog visibility settings

### Exposure Policies

Determine how a contract is made available to consumers:

| Policy | Description |
|--------|-------------|
| `tenant-scoped` | URLs include tenant identifiers; requires scope parameters |
| `global-control-plane` | Shared across all tenants; no scoping required |
| `private` | Not exposed in the public catalog |

### Governance Metadata

Every exposed contract is stamped with audit metadata under a configurable extension namespace (default: `x-governance`). This includes the stipulation ID, a SHA-256 hash of the stipulation for non-repudiation, timestamps, and custom audit notes.

### The Governance Pipeline

```
Backend Service → Ingest → Validate → Transform → Expose → Client
                    ↓          ↓           ↓          ↓
              RawContract  Stipulation  ProxyURLs  ExposedContract
                           Policies     Methods     + Metadata
                                        Metadata
```

1. **Ingest** — Store the raw OpenAPI spec from a backend service
2. **Validate** — Check the contract against stipulation policies
3. **Transform** — Rewrite URLs, strip methods, inject metadata
4. **Expose** — Create a governed contract safe for client consumption

---

## Basic Usage

### Ingest, Validate, Transform, Expose

```python
from contract_governor import ContractGovernor, StipulationConfig, ExposurePolicy
from contract_governor.core.registry import InMemoryContractRegistry

# 1. Define a stipulation policy
stipulation = StipulationConfig(
    stipulation_id="my-api:v1",
    exposure_policy=ExposurePolicy.TENANT_SCOPED,
    proxy_prefix_format="/tenant/{tenant_id}/my-api/v1",
    requires_scope_parameter=True,
    forbid_methods=["delete", "patch"],
    inject_metadata=True,
    metadata_block={
        "audit_note": "All requests brokered by control-plane",
        "tenant_isolation": True,
    },
    extension_namespace="x-governance",
)

# 2. Initialize the governor
registry = InMemoryContractRegistry()
governor = ContractGovernor(
    registry=registry,
    stipulations={"my-api:v1": stipulation},
)

# 3. Ingest a raw backend contract
openapi_spec = {
    "openapi": "3.0.3",
    "info": {"title": "My API", "version": "1.0.0"},
    "servers": [{"url": "http://backend.internal:8080"}],
    "paths": {
        "/items": {
            "get": {"summary": "List items", "responses": {"200": {"description": "OK"}}},
            "post": {"summary": "Create item", "responses": {"201": {"description": "Created"}}},
            "delete": {"summary": "Delete all", "responses": {"204": {"description": "Deleted"}}},
        }
    },
}

raw_record = governor.ingest_backend_contract(
    contract=openapi_spec,
    category="my-api",
    api_major="v1",
    source_service="backend-service",
    contract_file_path="contracts/my-api/v1/openapi.yaml",
)

# 4. Expose the contract (validates + transforms automatically)
exposed = governor.expose_contract(
    category="my-api",
    api_major="v1",
    gateway_base_url="https://api.example.com",
    scope_parameters={"tenant_id": "acme"},
)

# The exposed contract has:
# - Internal URLs replaced with proxy URLs
# - DELETE method stripped (forbidden by stipulation)
# - Governance metadata injected
print(exposed.exposed_openapi_spec["servers"])
# [{"url": "https://api.example.com/tenant/acme/my-api/v1", ...}]

print("delete" in exposed.exposed_openapi_spec["paths"]["/items"])
# False — stripped by stipulation
```

### Using the Validation Pipeline Directly

```python
from contract_governor.core.models import ExposurePolicy, StipulationConfig
from contract_governor.validation import ValidationPipeline

stipulation = StipulationConfig(
    exposure_policy=ExposurePolicy.TENANT_SCOPED,
    proxy_prefix_format="/tenant/{tenant_id}/api/v1",
    requires_scope_parameter=True,
    forbid_methods=["delete"],
)

pipeline = ValidationPipeline(stipulation)
result = pipeline.validate(my_openapi_spec)

if result.is_valid:
    print("Contract passes all stipulation checks")
else:
    for error in result.errors:
        print(f"[{error.code}] {error.message}")
```

### Using the Transformation Pipeline Directly

```python
from contract_governor.core.models import StipulationConfig, TransformContext, ExposurePolicy
from contract_governor.transformation import TransformationPipeline

stipulation = StipulationConfig(
    exposure_policy=ExposurePolicy.TENANT_SCOPED,
    proxy_prefix_format="/tenant/{tenant_id}/evidence-query/v1",
    requires_scope_parameter=True,
    forbid_methods=["delete", "patch"],
    inject_metadata=True,
    metadata_block={"audit_note": "Governed by stipulation policy"},
    extension_namespace="x-governance",
)

context = TransformContext(
    category="evidence-query",
    api_major_version="v1",
    contract_version="1.0.0",
    gateway_base_url="https://api.example.com",
    scope_parameters={"tenant_id": "acme"},
    target_audience="public",
)

pipeline = TransformationPipeline(stipulation)

# Preview changes before applying
preview = pipeline.preview_transformation(raw_contract, context)
print(preview["estimated_changes"])

# Apply transformation
transformed = pipeline.transform(raw_contract, context)
```

---

## Stipulation Configuration

Stipulations are defined in YAML files. The filename convention is `{category}_{api_major}.yaml`.

### Full YAML Reference

```yaml
# Unique identifier for this stipulation
stipulation_id: "evidence-query:v1"

# Semantic version of this stipulation policy
stipulation_version: "1.0.0"

# Exposure policy: "tenant-scoped", "global-control-plane", or "private"
exposure_policy: "tenant-scoped"

# URL template for proxy routing (supports {tenant_id}, {scope_id}, {organization_id})
proxy_prefix_format: "/tenant/{tenant_id}/evidence-query/v1"

# Whether a scope parameter (e.g., tenant_id) is required in the URL
requires_scope_parameter: true

# HTTP methods to strip from exposed contracts
forbid_methods:
  - "delete"
  - "patch"

# Required fields that must exist in the OpenAPI spec
required_fields:
  - "openapi"
  - "info.title"
  - "info.version"
  - "paths"

# Required OpenAPI version prefix
require_openapi_major: "3."

# Whether to enforce that contract version aligns with API major version
enforce_version_alignment: true

# Whether to inject governance metadata into exposed contracts
inject_metadata: true

# Custom metadata block injected into exposed contracts
metadata_block:
  audit_note: "All requests brokered by control-plane and logged"
  tenant_isolation: true
  data_classification: "tenant-scoped"

# Extension namespace for injected metadata (must start with "x-")
extension_namespace: "x-governance"

# Whether this contract appears in the API catalog
catalog_default_visible: true

# Server URL overrides (optional)
server_urls:
  - name: "EXTERNAL"
    url_template: "https://${GATEWAY_HOST}/api/v1"
    description: "External gateway"

# Deployment targeting (optional) — controls which pods mount this contract
mount_on:
  - "control-plane-controller"
# exclude_from:
#   - "control-plane-api"
```

### Exposure Policies Explained

**`tenant-scoped`** — Each tenant gets isolated URLs. Requires `requires_scope_parameter: true` and a `proxy_prefix_format` containing `{tenant_id}`.

```yaml
exposure_policy: "tenant-scoped"
proxy_prefix_format: "/tenant/{tenant_id}/my-api/v1"
requires_scope_parameter: true
```

**`global-control-plane`** — Shared across all tenants. No scoping required.

```yaml
exposure_policy: "global-control-plane"
proxy_prefix_format: "/api/my-service/v1"
requires_scope_parameter: false
```

**`private`** — Not exposed in the public catalog. Used for internal-only contracts.

```yaml
exposure_policy: "private"
catalog_default_visible: false
```

---

## FastAPI Integration

> Requires: `pip install contract-governor[server]`

### Router Generation from Contracts

The `ContractGovernorFastAPIExtension` generates FastAPI routes directly from your governed OpenAPI contracts:

```python
from fastapi import FastAPI
from contract_governor import ContractGovernor
from contract_governor.extensions.fastapi_extension import ContractGovernorFastAPIExtension

app = FastAPI()

# After setting up your governor with ingested + exposed contracts...
extension = ContractGovernorFastAPIExtension(governor)
router = extension.generate_fastapi_router()

app.include_router(router, prefix="/api")
```

### Implementation Registry

Map `operationId` values from your OpenAPI contracts to actual handler functions:

```python
from contract_governor.integrations.implementation_registry import ImplementationRegistry

# Create registry and register handlers
registry = ImplementationRegistry()
registry.register("listEvidence", list_evidence_handler)
registry.register("getEvidence", get_evidence_handler)
registry.register("createEvidence", create_evidence_handler)

# Pass to governor
governor = ContractGovernor(
    registry=contract_registry,
    stipulations=stipulations,
    implementation_registry=registry,
)
```

### Catalog Server with Scalar Documentation

Serve a browsable API catalog with interactive documentation:

```python
from contract_governor.integrations.fastapi_server import FastAPIAppFactory
from contract_governor.integrations.scalar_renderer import ScalarDocumentationRenderer
from contract_governor.integrations.catalog_providers import (
    ContractGovernorCatalogProvider,
    ContractGovernorContractProvider,
    BasicHealthProvider,
)

# Create SOLID providers
catalog_provider = ContractGovernorCatalogProvider(governor)
contract_provider = ContractGovernorContractProvider(governor)
health_provider = BasicHealthProvider()

# Create the catalog app
app = FastAPIAppFactory.create_catalog_app(
    catalog_provider=catalog_provider,
    contract_provider=contract_provider,
    health_provider=health_provider,
    documentation_renderer=ScalarDocumentationRenderer(),
    title="My API Catalog",
)

# Endpoints available:
# GET /api-catalog              — List all exposed contracts
# GET /api-catalog/docs         — Scalar documentation for catalog
# GET /contracts/{category}/{version}/openapi.json — Contract spec
# GET /contracts/{category}/{version}/docs         — Scalar docs per contract
# GET /health                   — Liveness probe
# GET /ready                    — Readiness probe
```

### Full Bootstrap (Contracts from S3)

For production deployments loading contracts from S3:

```python
from fastapi import FastAPI
from contract_governor.integrations.fastapi_server import mount_contract_governor

app = FastAPI()

governor = mount_contract_governor(
    app=app,
    implementation_registry=my_registry,
    s3_bucket="my-contracts-bucket",
    control_plane_version="v1.0.0",
    mount_prefix="/api",
    gateway_base_url="https://api.example.com",
)
```

---

## Multi-Tenant Setup

### Tenant-Scoped URLs

Configure stipulations to include tenant identifiers in all proxy URLs:

```yaml
# stipulations/my-api_v1.yaml
exposure_policy: "tenant-scoped"
proxy_prefix_format: "/tenant/{tenant_id}/my-api/v1"
requires_scope_parameter: true
```

### Exposing Contracts Per Tenant

```python
# Expose for a specific tenant
exposed = governor.expose_contract(
    category="my-api",
    api_major="v1",
    gateway_base_url="https://api.example.com",
    scope_parameters={"tenant_id": "acme-corp"},
)

# The proxy prefix resolves to: /tenant/acme-corp/my-api/v1
print(exposed.proxy_prefix)
# "/tenant/{tenant_id}/my-api/v1"

# Get the resolved URL for a specific tenant
url = exposed.get_proxy_url_for_tenant("acme-corp")
# "/tenant/acme-corp/my-api/v1"
```

### Multi-Tenant Contract Expansion

Expand a single contract template into multiple tenant-specific instances:

```python
# Expand templates for all configured tenants
instances = governor.expand_multi_tenant_contracts(
    category="my-api",
    api_major="v1",
)

for instance in instances:
    print(f"Tenant: {instance.tenant_id}, URL: {instance.proxy_url}")
```

### Tenant Request Resolution

Resolve an incoming request path to the correct backend URL:

```python
backend_url = governor.resolve_tenant_request("/tenant/acme/my-api/v1/items")
# Returns the backend URL for the matched contract
```

---

## URL Rewriting

The transformation pipeline rewrites internal backend URLs to safe proxy URLs.

### Template Variables

Stipulation `proxy_prefix_format` supports template variables:

```yaml
proxy_prefix_format: "/tenant/{tenant_id}/evidence-query/v1"
```

Available placeholders:
- `{tenant_id}` — Tenant identifier from scope parameters
- `{scope_id}` — Generic scope identifier
- `{organization_id}` — Organization identifier

### Server URL Templates with Environment Variables

Use `server_urls` for environment-specific URL resolution with `${VARIABLE}` syntax:

```yaml
server_urls:
  - name: "EXTERNAL"
    url_template: "https://${GATEWAY_HOST}/${API_PREFIX}/v1"
    description: "External gateway endpoint"
  - name: "INTERNAL"
    url_template: "http://${INTERNAL_HOST}:8080/v1"
    description: "Internal service mesh endpoint"
```

### How URL Rewriting Works

Given a raw contract with internal servers:

```yaml
servers:
  - url: http://backend-service.internal:8080
    description: Internal backend
```

After transformation with `gateway_base_url="https://api.example.com"` and `proxy_prefix_format="/tenant/{tenant_id}/my-api/v1"`:

```yaml
servers:
  - url: https://api.example.com/tenant/{tenant_id}/my-api/v1
    description: Governed proxy endpoint
```

---

## Security Enforcement

### Method Stripping

Forbid dangerous HTTP methods from being exposed to clients:

```yaml
forbid_methods:
  - "delete"   # Prevents data destruction
  - "patch"    # Prevents partial updates (if not desired)
  - "put"      # Prevents full replacements (if not desired)
```

The transformation pipeline removes these methods from all paths in the exposed contract. If a path has no remaining methods after stripping, the entire path is removed.

### Authentication Requirements

Enforce that all operations in the contract require authentication by validating the presence of security schemes:

```python
from contract_governor.validation import ValidationPipeline

# The validation pipeline checks security requirements
# based on the stipulation's exposure policy.
# Tenant-scoped contracts are validated for proper
# scope parameter presence in the URL template.
```

### Deployment Role Filtering

Control which deployment pods mount specific contracts:

```yaml
# Only mount on controller pods
mount_on:
  - "control-plane-controller"

# Or exclude from specific roles
exclude_from:
  - "control-plane-api"
```

In your deployment, set the `DEPLOYMENT_ROLE` environment variable:

```bash
export DEPLOYMENT_ROLE=control-plane-controller
```

The bootstrapper automatically filters contracts based on this role.

---

## Audit Compliance

### Metadata Injection

Every exposed contract receives governance metadata under the configured extension namespace:

```json
{
  "x-governance": {
    "capability_category": "evidence-query",
    "api_major_version": "v1",
    "contract_version": "1.0.2",
    "stipulation_id": "evidence-query:v1",
    "stipulation_version": "1.0.0",
    "stipulation_hash": "sha256:a1b2c3d4...",
    "exposed_by": "ContractGovernor-backend-service",
    "exposed_at": "2024-01-15T10:30:00Z",
    "audit_note": "All requests brokered by control-plane",
    "tenant_scope": "acme",
    "access_level": "public"
  }
}
```

### Stipulation Hashes for Non-Repudiation

Each stipulation generates a deterministic SHA-256 hash of its configuration. This hash is embedded in every exposed contract, providing:

- **Non-repudiation** — Proof of which policy was applied
- **Change detection** — If the stipulation changes, the hash changes
- **Audit trail** — Link exposed contracts back to the exact policy version

```python
# Get the hash of a stipulation
hash_value = stipulation.get_stipulation_hash()
# "a1b2c3d4e5f6..."

# The hash is stored in every exposed contract record
print(exposed.stipulation_hash)
```

### Governance Status

Query the full governance status of any contract:

```python
status = governor.get_governance_status("my-api", "v1")

print(status)
# {
#   "category": "my-api",
#   "api_major_version": "v1",
#   "has_raw_contract": True,
#   "has_exposed_contract": True,
#   "has_stipulation": True,
#   "governance_complete": True,
#   "raw_contract_info": {...},
#   "exposed_contract_info": {...},
#   "stipulation_info": {...}
# }
```

---

## Configuration Sources

Contract Governor supports multiple backends for loading stipulation configurations.

### LocalFile (Development)

```python
from contract_governor.config import LocalFileConfigSource

# Load stipulations from a local directory
source = LocalFileConfigSource(config_dir="config/stipulations")

# Load all stipulations
stipulations = source.load_stipulations()
# Returns: {"evidence-query:v1": StipulationConfig(...), ...}

# Load a specific stipulation
config = source.load_stipulation("evidence-query", "v1")

# Save a stipulation
source.save_stipulation("my-api", "v1", my_stipulation_config)

# List available categories and versions
categories = source.list_categories()
versions = source.list_versions("evidence-query")
```

File naming convention: `{category}_{api_major}.yaml` (e.g., `evidence-query_v1.yaml`).

### S3 (Cloud Deployments)

> Requires: `pip install contract-governor[aws]`

```python
from contract_governor.config import S3ConfigSource

# Load stipulations from S3
source = S3ConfigSource(
    bucket_name="my-governance-bucket",
    prefix="stipulations/",
    region="us-east-1",
)

# Load all stipulations
stipulations = source.load_stipulations()

# Load a specific stipulation
config = source.load_stipulation("evidence-query", "v1")

# Save/delete stipulations
source.save_stipulation("my-api", "v1", config)
source.delete_stipulation("my-api", "v1")

# Check availability
if source.is_available():
    print("S3 bucket accessible")
```

S3 key structure: `{prefix}{category}/{api_major}.json`

### DynamoDB (Scalable Cloud Deployments)

> Requires: `pip install contract-governor[aws]`

```python
from contract_governor.config import DynamoDBConfigSource

# Load stipulations from DynamoDB
source = DynamoDBConfigSource(
    table_name="contract-stipulations",
    region="us-east-1",
)

# Load all stipulations (scans the table)
stipulations = source.load_stipulations()

# Load a specific stipulation (direct key lookup)
config = source.load_stipulation("evidence-query", "v1")

# Save/delete
source.save_stipulation("my-api", "v1", config)
source.delete_stipulation("my-api", "v1")
```

DynamoDB table schema:
- Partition key: `category` (String)
- Sort key: `api_major_version` (String)

### Loading Contracts from S3

> Requires: `pip install contract-governor[aws]`

```python
from contract_governor.loaders.s3_loader import S3ContractSource
import boto3

s3_client = boto3.client("s3")

source = S3ContractSource(
    s3_client=s3_client,
    bucket_name="my-contracts-bucket",
    control_plane_version="v1.0.0",
    contracts_prefix="contracts",
    stipulations_prefix="stipulations",
)

# Load all contracts from S3
contracts = source.load_contracts()

# Ingest into governor
for contract_data in contracts:
    governor.ingest_backend_contract(
        contract=contract_data["contract"],
        category=contract_data["category"],
        api_major=contract_data["api_major"],
        source_service=contract_data["source_service"],
        contract_file_path=contract_data["contract_file_path"],
    )

# Load stipulations from S3
stipulations = source.load_stipulations()
```

S3 contract structure: `{major_version}/{contracts_prefix}/{category}/{version}/openapi.yaml`

---

## Deployment Patterns

### Standalone (Development)

```python
# main.py
import uvicorn
from fastapi import FastAPI
from contract_governor import ContractGovernor, StipulationConfig
from contract_governor.config import LocalFileConfigSource
from contract_governor.core.registry import InMemoryContractRegistry
from contract_governor.extensions.fastapi_extension import ContractGovernorFastAPIExtension

app = FastAPI(title="Contract Governor")

# Load stipulations from local files
config_source = LocalFileConfigSource("config/stipulations")
stipulations = config_source.load_stipulations()

# Initialize governor
registry = InMemoryContractRegistry()
governor = ContractGovernor(registry=registry, stipulations=stipulations)

# ... ingest contracts, expose them ...

# Generate and mount router
extension = ContractGovernorFastAPIExtension(governor)
router = extension.generate_fastapi_router()
app.include_router(router, prefix="/api")

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
```

### Docker

```dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY pyproject.toml .
RUN pip install contract-governor[server,aws]

COPY . .

ENV LOG_LEVEL=INFO
ENV STRUCTURED_LOGGING=true
ENV SERVICE_NAME=contract-governor

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

```bash
# Build and run
docker build -t contract-governor:latest .
docker run -p 8000:8000 \
  -e LOG_LEVEL=INFO \
  -e DEPLOYMENT_ROLE=control-plane-controller \
  -e AWS_REGION=us-east-1 \
  contract-governor:latest
```

### Kubernetes / EKS

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: contract-governor
  labels:
    app: contract-governor
spec:
  replicas: 2
  selector:
    matchLabels:
      app: contract-governor
  template:
    metadata:
      labels:
        app: contract-governor
    spec:
      containers:
        - name: app
          image: contract-governor:latest
          ports:
            - containerPort: 8000
          env:
            - name: LOG_LEVEL
              value: "INFO"
            - name: STRUCTURED_LOGGING
              value: "true"
            - name: SERVICE_NAME
              value: "contract-governor"
            - name: DEPLOYMENT_ROLE
              value: "control-plane-controller"
            - name: AWS_REGION
              valueFrom:
                configMapKeyRef:
                  name: app-config
                  key: aws-region
          livenessProbe:
            httpGet:
              path: /health
              port: 8000
            initialDelaySeconds: 10
            periodSeconds: 30
          readinessProbe:
            httpGet:
              path: /ready
              port: 8000
            initialDelaySeconds: 5
            periodSeconds: 10
          resources:
            requests:
              memory: "256Mi"
              cpu: "250m"
            limits:
              memory: "512Mi"
              cpu: "500m"
---
apiVersion: v1
kind: Service
metadata:
  name: contract-governor
spec:
  selector:
    app: contract-governor
  ports:
    - port: 80
      targetPort: 8000
  type: ClusterIP
```

```bash
# Deploy
kubectl apply -f deployment/kubernetes/

# Verify health
curl http://contract-governor.default.svc.cluster.local/health
curl http://contract-governor.default.svc.cluster.local/ready
```

---

## Troubleshooting

### ImportError: FastAPI is required for this module

**Cause:** You're trying to use FastAPI integration without the `[server]` extra installed.

**Fix:**
```bash
pip install contract-governor[server]
```

### ImportError: boto3 is required

**Cause:** You're using S3 or DynamoDB config sources without the `[aws]` extra.

**Fix:**
```bash
pip install contract-governor[aws]
```

### StipulationNotFoundError

**Cause:** No stipulation file exists for the category and version you're trying to expose.

**Fix:** Create a stipulation file matching the naming convention:
```bash
# For category "my-api" version "v1":
config/stipulations/my-api_v1.yaml
```

### StipulationParseError

**Cause:** A stipulation file exists but contains invalid YAML or unrecognized fields.

**Fix:** Check the file for syntax errors. Unknown fields are logged as warnings and filtered out. Required fields like `exposure_policy` must be present.

### StipulationViolationError

**Cause:** A contract fails validation against its stipulation policy.

**Fix:** Check the validation result for specific errors:
```python
try:
    governor.expose_contract(category="my-api", api_major="v1", ...)
except StipulationViolationError as e:
    for error in e.validation_result.errors:
        print(f"[{error.code}] {error.message}")
```

Common violations:
- Contract uses a forbidden HTTP method
- Missing required fields (e.g., `info.title`)
- OpenAPI version mismatch (e.g., using 2.x when 3.x is required)
- Version alignment failure (e.g., contract version `2.0.0` with API major `v1`)

### ContractNotFoundError

**Cause:** Attempting to expose a contract that hasn't been ingested yet.

**Fix:** Ensure you call `ingest_backend_contract()` before `expose_contract()`:
```python
governor.ingest_backend_contract(contract=spec, category="my-api", api_major="v1", ...)
governor.expose_contract(category="my-api", api_major="v1", ...)
```

### Contracts Not Appearing in Catalog

**Possible causes:**
1. `catalog_default_visible: false` in the stipulation
2. Contract failed validation (check logs for `StipulationViolationError`)
3. Deployment role filtering excluded the contract (check `DEPLOYMENT_ROLE` env var)
4. Contract was not exposed (only exposed contracts appear in the catalog)

### Validation Passes But Methods Still Present

**Cause:** Validation and transformation are separate steps. Validation *checks* for forbidden methods; transformation *strips* them.

**Fix:** This is expected behavior. The validation pipeline reports forbidden methods as errors. If you want to strip them silently, set `forbid_methods` in the stipulation and use the full `expose_contract()` flow which runs both validation and transformation.

### Logging Configuration

Enable detailed logging to diagnose issues:

```python
from contract_governor.logging import set_logging_config
import logging

# Enable debug logging for contract-governor
set_logging_config(logging.DEBUG)
```

Or via environment variable:
```bash
export LOG_LEVEL=DEBUG
```

### Health Check Endpoints

When using the FastAPI catalog server, health endpoints are available:

- `GET /health` — Returns `200` if the service is alive
- `GET /ready` — Returns `200` if the service is ready to serve requests

Use these for Kubernetes liveness and readiness probes.
