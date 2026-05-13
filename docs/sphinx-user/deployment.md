# Deployment

## Prerequisites

- Python 3.11+
- AWS account with S3 access (for contract storage)
- FastAPI application (primary integration target)

## Installation

```bash
pip install contract-governor
# With AWS support:
pip install contract-governor[aws]
```

## FastAPI Integration

```python
from fastapi import FastAPI
from contract_governor.extensions import ContractGovernorFastAPIExtension

app = FastAPI()
extension = ContractGovernorFastAPIExtension(app, config_dir="config/")
extension.load_stipulations()
```

## S3 Contract Publishing

Publish contracts and stipulations to S3 for centralized management:

```bash
python tools/publish_to_s3.py \
  --contracts-dir config/contracts/ \
  --stipulations-dir config/stipulations/ \
  --bucket my-contract-bucket \
  --version v1.0.0
```

## Documentation Publishing

Build and publish Sphinx documentation to S3:

```bash
./scripts/sync-docs.sh --bucket=my-docs-bucket --profile=my-profile
```

This publishes both user and developer documentation:
- `s3://bucket/user/` — User guides
- `s3://bucket/developer/` — API reference
