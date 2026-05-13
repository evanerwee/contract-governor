# Configuration Reference

## Stipulation Fields

See [Stipulation Authoring](stipulations.md) for the full field reference.

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `DOCS_BUCKET` | `contract-governor-docs` | S3 bucket for documentation |
| `AWS_PROFILE` | `default` | AWS CLI profile for S3 operations |
| `AWS_REGION` | `us-east-1` | AWS region |
| `DJANGO_SECRET_KEY` | (none) | Django secret key (if using Django integration) |

## Config Files

| File | Location | Purpose |
|------|----------|---------|
| `config/stipulations/*.yaml` | Project root | Stipulation definitions |
| `config/schema.json` | Project root | Stipulation JSON schema |
| `config/template_schema.json` | Project root | Template JSON schema |
| `pyproject.toml` | Project root | Package and tool configuration |
