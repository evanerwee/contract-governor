# Core Concepts

## Contracts

An OpenAPI specification that describes an API. Contract Governor manages the
lifecycle of these contracts — loading, validating, transforming, and exposing them.

## Stipulations

A stipulation is a governance policy applied to a contract. It defines:

- **Exposure policy** — Who can see the contract (global, tenant-scoped, admin-only)
- **Proxy prefix** — How URLs are rewritten for the target environment
- **Validation rules** — What checks must pass before the contract is exposed
- **Implementation binding** — Which code module implements the contract's operations

## Exposure Policies

| Policy | Description |
|--------|-------------|
| `global-data-plane` | Visible to all data planes |
| `global-control-plane` | Visible to control plane services |
| `tenant-scoped` | Visible only within a tenant's scope |
| `admin-only` | Restricted to administrative access |

## Transformation Pipeline

Contracts pass through a transformation pipeline before exposure:

1. **Validation** — Schema correctness, required fields, operationId presence
2. **URL rewriting** — Proxy prefix injection, path parameter resolution
3. **Metadata injection** — Audit trail, stipulation hash, governance tags
4. **Exposure** — Mount on the target framework (FastAPI, Flask, Django)

## Entitlements

Entitlements control which users and groups can access specific contracts
and operations. They integrate with SpiceDB for fine-grained authorization.
