# Contract Templates

Templates allow you to define a contract once and instantiate it for multiple
tenants or environments with variable substitution.

## Template Format

```yaml
template_id: evidence-query-template
base_contract: evidence-query/v2.0.0/evidence_query_api.yaml
variables:
  - name: tenant_id
    description: "Tenant identifier"
  - name: environment
    description: "Deployment environment"
    default: "production"
```

## Variable Substitution

Variables in the OpenAPI spec are replaced at instantiation time. Use
`{variable_name}` syntax in paths, descriptions, and server URLs.

## Discovery Sources

Templates can auto-discover variable values from external sources
(DynamoDB, S3, API calls) to generate contract instances automatically.
