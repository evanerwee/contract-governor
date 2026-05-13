# Troubleshooting

## Common Issues

### Stipulation not found

```
❌ Stipulation not found: src/.../stipulations/my-service_v1.yaml
```

Check that the stipulation file exists and the service name matches the
filename pattern: `{service_name}_v1.yaml`.

### Router has no routes

```
❌❌❌ ROUTER IS EMPTY - NO ROUTES! ❌❌❌
```

The implementation module's factory function returns an object, but its
router has no registered routes. Ensure `_setup_routes()` is called in
the constructor.

### OperationId mismatch

```
❌ MISSING: my_operation() for GET /path
```

Contract Governor converts camelCase operationIds to snake_case function
names. Ensure your implementation method matches:
- `getUsers` → `get_users()`
- `createOrder` → `create_order()`

### Import errors during verification

Ensure the implementation module's dependencies are installed and the
`sys.path` includes the source directory.

## Verification Tool

Run the full verification suite:

```bash
python tools/verify_contract_governor_setup.py <service_name>
```

With auto-remediation:

```bash
python tools/verify_contract_governor_setup.py <service_name> --rem
```
