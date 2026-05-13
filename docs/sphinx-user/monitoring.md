# Monitoring

## Health Endpoints

Contract Governor registers standard health endpoints when using the
server integrations:

| Endpoint | Purpose |
|----------|---------|
| `GET /health` | Liveness probe |
| `GET /ready` | Readiness probe |
| `GET /info` | Service information |

## Metrics

The monitoring module provides decorators for tracking:

- Contract load times
- Validation pass/fail rates
- Transformation pipeline duration
- Catalog request counts

## Logging

Configure logging via the `contract_governor.logging` module. Supports
structured JSON output for CloudWatch and ELK integration.
