# CLI Tools Reference

## verify_contract_governor_setup.py

Verify that a service's stipulation, OpenAPI contract, and implementation
are consistent.

```bash
python tools/verify_contract_governor_setup.py <service_name> [options]
```

| Flag | Description |
|------|-------------|
| `--rem` | Auto-generate missing `_setup_routes()` code |
| `--test-entitlements` | Run entitlement integration tests |
| `--test-security-context-sync` | Run SpiceDB sync tests |

## publish_to_s3.py

Publish contracts and stipulations to an S3 bucket with manifest generation.

```bash
python tools/publish_to_s3.py --contracts-dir DIR --bucket BUCKET --version VERSION
```

## generate_stipulation.py

Generate stipulation files from OpenAPI contracts with intelligent defaults.

```bash
python tools/generate_stipulation.py <contract_file>
```

## generate_entitlements.py

Generate SpiceDB entitlement manifests from OpenAPI contracts.

```bash
python tools/generate_entitlements.py --contract <file_or_url> --format manifest
```

## sync-docs.sh

Build and sync Sphinx documentation to S3.

```bash
./scripts/sync-docs.sh [--skip-build] [--developer-only] [--user-only]
```
