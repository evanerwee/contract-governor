# Contract Governor v2.0.1

A governance framework for OpenAPI contracts that enforces security policies, tenant isolation, and audit compliance through validation, transformation, and controlled exposure.

## Why Do You Need an OpenAPI Contract Governor?

### The Problem

Backend services expose OpenAPI contracts that contain:
- ❌ Internal service URLs (`http://backend-service.internal:8080`)
- ❌ Unsafe HTTP methods (DELETE, PATCH on production data)
- ❌ No audit trail or governance metadata
- ❌ No tenant isolation in multi-tenant systems
- ❌ Direct exposure of internal API structure

**Exposing these contracts directly to clients is a security risk.**

### The Solution

Contract Governor acts as a **governance layer** between your backend services and clients:

```
Backend APIs → Contract Governor → Safe, Governed APIs → Clients
   (unsafe)      (governance)         (safe, audited)     (protected)
```

### What It Does

1. **Security Enforcement**
   - Strips dangerous HTTP methods (DELETE, PATCH)
   - Enforces authentication requirements
   - Validates contract structure

2. **URL Rewriting**
   - Replaces internal URLs with safe proxy URLs
   - Supports environment-specific URLs (prod, staging, dev)
   - Template-based URL resolution with `${VARIABLES}`

3. **Multi-Tenant Isolation**
   - Tenant-scoped URLs: `/tenant/{tenant_id}/api/v1`
   - Prevents cross-tenant data access
   - Enforces tenant parameter validation

4. **Audit Compliance**
   - Injects governance metadata into every contract
   - Non-repudiation with stipulation hashes
   - Complete transformation audit trail

5. **API Versioning**
   - Support multiple contract versions simultaneously
   - Version alignment validation
   - Backward compatibility enforcement

## Overview

Contract Governor ensures backend API contracts are never directly exposed to clients. Instead, contracts are:

1. **Ingested** from backend services (stored as raw, internal-only contracts)
2. **Validated** against stipulation policies (security, versioning, tenant scoping)
3. **Transformed** with safe URLs, method filtering, and audit metadata
4. **Exposed** as governed contracts safe for client consumption
5. **Documented** via Scalar or custom renderers

## Key Features

- 🔒 **Security Enforcement** - Forbid dangerous HTTP methods, enforce authentication
- 🏢 **Multi-Tenant Isolation** - Tenant-scoped URLs with parameter validation
- 📋 **Audit Compliance** - Non-repudiation tracking with stipulation hashes
- 🔄 **API Versioning** - Support multiple contract versions simultaneously
- 🌐 **URL Template Resolution** - Environment variable substitution in server URLs
- 📦 **Multiple Environments** - Support PROD, DEV, STAGING with named URLs
- 🎨 **Extensible** - Add custom validators, transformers, and renderers
- 🏗️ **SOLID Architecture** - Clean separation of concerns, dependency injection

## Use Cases

- **API Gateway**: Govern contracts before exposing to external clients
- **Multi-Tenant SaaS**: Enforce tenant isolation at the contract level
- **Microservices**: Centralize contract governance across services
- **Compliance**: Maintain audit trail for all API exposures
- **Security**: Prevent accidental exposure of internal APIs

## Architecture

```
Backend Services → Raw Contracts → Validation → Transformation → Exposed Contracts → Clients
                        ↓              ↓              ↓                ↓
                   (Internal)    (Stipulations)  (Proxy URLs)    (Catalog/Docs)
```

### Core Components

- **ContractGovernor** - Orchestrates ingestion, validation, transformation, exposure
- **ValidationPipeline** - Enforces stipulation policies (methods, versions, scoping)
- **TransformationPipeline** - Rewrites URLs, strips methods, injects audit metadata
- **ContractRegistry** - Stores raw (internal) and exposed (public) contracts separately
- **FastAPICatalogServer** - Serves catalog and contracts via HTTP endpoints
- **ScalarDocumentationRenderer** - Generates interactive API documentation

## Quick Start

### Installation

```bash
# From PyPI
pip install contract-governor

# For development (editable install with dev extras)
pip install -e ".[dev]"
```

### Basic Usage

```python
from contract_governor.core.contract_governor import ContractGovernor
from contract_governor.core.registry import InMemoryContractRegistry
from contract_governor.core.models import StipulationConfig, ExposurePolicy

# Create stipulation
stipulation = StipulationConfig(
    exposure_policy=ExposurePolicy.TENANT_SCOPED,
    proxy_prefix_format="/tenant/{tenant_id}/api/v1",
    requires_scope_parameter=True,
    forbid_methods=["delete", "patch"]
)

# Initialize governor
registry = InMemoryContractRegistry()
governor = ContractGovernor(registry, {"api:v1": stipulation})

# Ingest backend contract
governor.ingest_backend_contract(
    contract=openapi_spec,
    category="api",
    api_major="v1",
    source_service="backend-service",
    contract_file_path="/path/to/contract.yaml"
)

# Expose contract with governance
exposed = governor.expose_contract(
    category="api",
    api_major="v1",
    gateway_base_url="https://api.example.com",
    scope_parameters={"tenant_id": "acme"}
)

# Access transformed contract
print(exposed.exposed_openapi_spec)
```

### FastAPI Server

```python
from contract_governor.integrations.fastapi_server import FastAPIAppFactory
from contract_governor.integrations.scalar_renderer import ScalarDocumentationRenderer

# Create providers (see examples/ for details)
catalog_provider = MyCatalogProvider(governor)
contract_provider = MyContractProvider(governor)
health_provider = MyHealthProvider()

# Create FastAPI app
app = FastAPIAppFactory.create_catalog_app(
    catalog_provider=catalog_provider,
    contract_provider=contract_provider,
    health_provider=health_provider,
    documentation_renderer=ScalarDocumentationRenderer()
)

# Run server
# uvicorn main:app --host 0.0.0.0 --port 8000
```

## Configuration

### Stipulation Configuration (YAML)

```yaml
stipulation_id: "evidence-query:v1"
exposure_policy: "tenant-scoped"
proxy_prefix_format: "/tenant/{tenant_id}/evidence-query/v1"
requires_scope_parameter: true
forbid_methods:
  - "delete"
  - "patch"
inject_metadata: true
metadata_block:
  audit_note: "All requests brokered by control-plane"
  tenant_isolation: true
extension_namespace: "x-governance"
```

### Configuration Sources (Stipulations)

- **LocalFileConfigSource** - YAML/JSON in `config/stipulations/`
- **S3ConfigSource** - Cloud-based stipulation storage
- **DynamoDBConfigSource** - Database-backed stipulation storage

### Contract Sources (OpenAPI Specs)

- **S3ContractSource** - Load contracts from S3 recursively

```python
from contract_governor.loaders.s3_loader import S3ContractSource
import boto3

# Load contracts from S3
s3_client = boto3.client('s3')
source = S3ContractSource(
    s3_client,
    bucket_name="my-contracts",
    prefix="contracts/",
    category_from_path=True,
    version_from_path=True
)

contracts = source.load_contracts()

# Ingest all contracts
for contract_data in contracts:
    governor.ingest_backend_contract(**contract_data)
```

## API Endpoints

### Catalog Server

- `GET /api-catalog` - List all exposed contracts
- `GET /api-catalog/docs` - Scalar documentation for catalog
- `GET /contracts/{category}/{api_major}/openapi.json` - Contract spec
- `GET /contracts/{category}/{api_major}/metadata` - Governance metadata
- `GET /contracts/{category}/{api_major}/docs` - Scalar documentation
- `GET /health` - Liveness probe
- `GET /ready` - Readiness probe

## Governance Metadata

Every exposed contract includes governance metadata:

```json
{
  "x-governance": {
    "capability_category": "evidence-query",
    "api_major_version": "v1",
    "contract_version": "1.0.2",
    "stipulation_id": "evidence-query:v1",
    "stipulation_hash": "sha256:...",
    "exposed_at": "2024-01-15T10:30:00Z",
    "tenant_scope": "acme",
    "audit_note": "All requests brokered by control-plane"
  }
}
```

## Extensibility

### Custom Validator

```python
from contract_governor.interfaces.validator import Validator


class CustomValidator(Validator):
    def validate(self, contract, stipulation):
        # Your validation logic
        return ValidationResult(is_valid=True)

    def get_validator_name(self):
        return "CustomValidator"
```

### Custom Transformer

```python
from contract_governor.interfaces.transformer import Transformer


class CustomTransformer(Transformer):
    def transform(self, contract, context, stipulation):
        # Your transformation logic
        return transformed_contract

    def get_execution_order(self):
        return 50
```

### Custom Renderer

```python
from contract_governor.interfaces.documentation_renderer import DocumentationRenderer


class CustomRenderer(DocumentationRenderer):
    def render_contract_page(self, contract_url, title):
        return f"<html>...</html>"
```

## Logging

### Basic Configuration

```python
from contract_governor.logging import set_logging_config
import logging

# Set logging level
set_logging_config(logging.INFO)

# Use logger
logger = logging.getLogger(__name__)
logger.info("Contract ingested")
```

### Advanced Configuration

```python
from contract_governor.logging import set_advanced_logging_config
import logging

# Configure with module filtering
set_advanced_logging_config(
    logging_level=logging.INFO,
    included_modules={logging.INFO: ['contract_governor.core']},
    excluded_modules={logging.INFO: ['boto', 'urllib']},
    filename='contract-governor.log'  # Optional file output
)
```

### Environment-Based Configuration

```python
import os
import logging
from contract_governor.logging import set_logging_config

# Configure from environment
log_level = os.getenv('LOG_LEVEL', 'INFO')
set_logging_config(log_level)
```

## Testing

```bash
# Run all tests
pytest

# Run specific test suite
pytest tests/test_e2e_integration.py -v

# Run with coverage
pytest --cov=contract_governor --cov-report=html
```

## Deployment

### Kubernetes/EKS

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: contract-governor
spec:
  template:
    spec:
      containers:
      - name: app
        image: contract-governor:latest
        env:
        - name: LOG_LEVEL
          value: "INFO"
        - name: STRUCTURED_LOGGING
          value: "true"
        - name: SERVICE_NAME
          value: "contract-governor"
```

```bash
# Apply deployment
kubectl apply -f deployment/kubernetes/

# Check health
curl http://service-url/health
curl http://service-url/ready

# View logs
kubectl logs -f deployment/contract-governor
```

### Docker

```bash
# Build image
docker build -t contract-governor:latest .

# Run with structured logging
docker run -p 8000:8000 \
  -e LOG_LEVEL=INFO \
  -e STRUCTURED_LOGGING=true \
  -e SERVICE_NAME=contract-governor \
  contract-governor:latest
```

## SOLID Principles

- **Single Responsibility** - Each class has one reason to change
- **Open/Closed** - Extend via validators/transformers without modifying core
- **Liskov Substitution** - Any implementation can replace another
- **Interface Segregation** - Focused interfaces (CatalogProvider, ContractProvider)
- **Dependency Inversion** - Depend on abstractions, inject dependencies

## Documentation

- [CHANGELOG.md](CHANGELOG.md) - Version history
- [CONTRIBUTING.md](CONTRIBUTING.md) - Development setup and contribution guidelines
- [examples/](examples/) - Usage examples for core workflows

## License

MIT License. Copyright (c) 2024-2026 Evan Erwee. See [LICENSE](LICENSE) for details.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.
