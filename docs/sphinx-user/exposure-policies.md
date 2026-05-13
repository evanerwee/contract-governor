# Exposure Policies

Exposure policies control the visibility and access scope of governed contracts.

## Policy Types

### `global-data-plane`

The contract is visible to all data plane services. Typically used for health
checks, system endpoints, and shared infrastructure APIs.

### `global-control-plane`

The contract is visible to control plane services. Used for authentication,
authorization, and administrative APIs.

### `tenant-scoped`

The contract is scoped to a specific tenant. The proxy prefix includes a
tenant or scope identifier. This is the default and most common policy.

### `admin-only`

The contract is restricted to administrative access. Not visible in the
public catalog.

## Choosing a Policy

| Use Case | Recommended Policy |
|----------|-------------------|
| Health/readiness probes | `global-data-plane` |
| Authentication endpoints | `global-control-plane` |
| Tenant-specific business APIs | `tenant-scoped` |
| Internal admin tools | `admin-only` |
