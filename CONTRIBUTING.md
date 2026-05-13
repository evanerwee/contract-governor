# Contributing to Contract Governor

Thank you for considering a contribution to Contract Governor.

## Before You Contribute

All contributors must agree to the [Contributor License Agreement](CLA.md)
before their first contribution can be accepted. By submitting a pull request,
you indicate your agreement to the CLA terms.

The CLA ensures that:
- You retain copyright to your work
- The project can continue to be distributed under the MIT License
- The Owner (Evan Erwee) maintains the right to manage the project's licensing

## Development Setup

```bash
# Clone the repository
git clone https://github.com/evanerwee/contract-governor.git
cd contract-governor

# Create and activate a virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install in editable mode with dev dependencies
pip install -e ".[dev]"
```

## How to Contribute

1. Fork the repository
2. Create a feature branch from `main`
3. Make your changes
4. Run the full quality check suite (see below)
5. Verify Sphinx docs build: `make html -C docs/sphinx`
6. Submit a pull request

## Running the Quality Check Suite

Run the full suite before submitting a PR. This mirrors what CI enforces:

```bash
# Linting
ruff check .

# Formatting
black --check .

# Type checking
mypy contract_governor/

# Tests
pytest

# Docstring coverage (must be ≥95%)
interrogate contract_governor/ --fail-under 95

# Security scan for dependency vulnerabilities
pip-audit
```

All checks must pass for a PR to be merged.

## Code Standards

- Python 3.11+
- Pydantic V2 (not V1)
- All public functions and classes must have docstrings
- Run `interrogate contract_governor/ --fail-under 95` to verify docstring coverage
- Run `pip-audit` to check for dependency vulnerabilities

## What We Accept

- Bug fixes with tests
- Documentation improvements
- New framework integrations (following the existing SOLID patterns)
- Performance improvements with benchmarks

## What Needs Discussion First

Open an issue before submitting PRs for:
- New features or capabilities
- Changes to the public API
- Dependency additions
- Architecture changes

## License

By contributing, you agree that your contributions will be licensed under the
project's [MIT License](LICENSE).
