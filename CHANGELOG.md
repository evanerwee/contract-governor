# Changelog

All notable changes to Contract Governor will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [2.0.1] - 2026-06-14

### 🚀 PyPI Readiness

Prepares `contract-governor` for extraction from the `aws-sso-admin` monorepo into a standalone repository (`github.com/evanerwee/contract-governor`) and publication to PyPI.

### ✨ Features

- **CI/CD Automation**: Added GitHub Actions workflow with matrix testing (Python 3.11, 3.12), linting, type checking, security scanning, build verification, and PyPI trusted publishing via OIDC
- **Security Scanning**: Integrated `pip-audit` for dependency vulnerability scanning on every PR
- **Docstring Coverage**: Integrated `interrogate` with ≥95% threshold enforcement on public APIs

### 🔧 Changed

- **Version Alignment**: Switched to dynamic versioning via `hatch` reading from `contract_governor/__init__.py` — eliminates version drift between `pyproject.toml` and source code
- **Metadata Correction**: Updated all project URLs from `contract-stipulations` to `contract-governor` pointing to `github.com/evanerwee/contract-governor`
- **Build Exclusions**: Configured hatchling to exclude `_archived/`, `Example/`, `scripts/`, `tools/`, `.hypothesis/`, and other non-distribution files from wheel and sdist artifacts

### 🗑️ Removed

- **Dead Code Removal (`_archived/`)**: Removed the `_archived/` directory containing legacy/unused modules. Rationale: these files were not imported by any module in the package, added confusion for contributors, inflated the distribution size, and had no public API surface. Historical context is preserved in git history.

### 📚 Documentation

- Added `CONTRIBUTING.md` with development setup and quality check instructions
- Updated `README.md` with PyPI installation instructions and standalone repo references
- Configured Sphinx to read version dynamically from `contract_governor.__version__`
- Added usage examples for contract validation and contract transformation workflows

---

## [1.3.0] - 2026-02-24

### ✨ Features

- **Deployment Targeting**: Control which contracts mount on which pods using `mount_on` and `exclude_from` fields in stipulation config
  - Set `DEPLOYMENT_ROLE` env var on your pod (e.g., `control-plane-api`, `control-plane-controller`)
  - Add `mount_on: ["control-plane-controller"]` to only mount on specific roles
  - Add `exclude_from: ["control-plane-api"]` to mount everywhere except specific roles
  - Zero runtime cost - filtering happens only at startup
  - Backward compatible - contracts without these fields mount everywhere

### 📚 Documentation

- Added `should_mount_for_role()` method to `StipulationConfig` for deployment role checking

---

## [1.1.0] - 2026-02-22

### 🐛 Bug Fixes

- **Automatic Route Sorting for FastAPI**: Fixed route collision bug where parameterized routes (e.g., `/files/{id}`) could shadow static routes (e.g., `/files/search`) when OpenAPI specs had incorrect path ordering
  - Added `sort_routes_for_fastapi()` function that automatically sorts paths before mounting
  - Static routes now always registered before parameterized routes at each path level
  - Backwards compatible - existing specs with correct order are unaffected
  - Applied to both `_generate_router_via_registry()` and `_generate_router_via_discovery()` methods

### 📚 Documentation

- Added `tests/test_route_sorting.py` with comprehensive test coverage for route sorting

---

## [1.0.2] - Initial Release

### ✨ Features

- **Contract Governance Framework**: Complete OpenAPI contract governance with validation, transformation, and controlled exposure
- **Security Enforcement**: Strip dangerous HTTP methods, enforce authentication requirements
- **URL Rewriting**: Replace internal URLs with safe proxy URLs, environment-specific URL support
- **Multi-Tenant Isolation**: Tenant-scoped URLs with parameter validation
- **Audit Compliance**: Governance metadata injection, stipulation hashes, transformation audit trail
- **API Versioning**: Multiple contract versions, version alignment validation
- **FastAPI Extension**: Generate FastAPI routers from OpenAPI contracts with implementation registry
- **Stipulation System**: YAML/JSON configuration for governance policies
- **Multiple Config Sources**: LocalFile, S3, DynamoDB stipulation storage
- **Scalar Documentation**: Interactive API documentation rendering

### 🏗️ Architecture

- SOLID principles throughout
- Dependency injection support
- Extensible validators, transformers, and renderers
- Clean separation between raw (internal) and exposed (public) contracts

---

## Known Issues

### Route Ordering (Fixed in 1.1.0)

FastAPI matches routes in registration order. If your OpenAPI spec defines `/files/{id}` before `/files/search`, requests to `/files/search` will incorrectly match the parameterized route. 

**Resolution**: Upgrade to 1.1.0+ which automatically sorts routes via `sort_routes_for_fastapi()`. No manual route ordering is required. For specs targeting older versions, ensure static routes (e.g., `/files/search`) are defined before parameterized routes (e.g., `/files/{id}`) in your OpenAPI paths.
