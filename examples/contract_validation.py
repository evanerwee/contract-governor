"""
Example: Validating an OpenAPI contract against governance rules.

This example demonstrates how to use contract-governor's ValidationPipeline
to check an OpenAPI contract for compliance with a stipulation policy.

The validation pipeline checks:
- OpenAPI version requirements
- Required fields presence
- Forbidden HTTP methods
- Tenant scoping compliance
- Version alignment between API major and contract version
"""

from contract_governor.core.models import ExposurePolicy, StipulationConfig
from contract_governor.validation import ValidationPipeline


def main():
    # Step 1: Define a stipulation policy that contracts must comply with.
    # This policy enforces tenant-scoped exposure, forbids DELETE and PATCH,
    # and requires OpenAPI 3.x contracts.
    stipulation = StipulationConfig(
        stipulation_id="example-tenant-policy",
        exposure_policy=ExposurePolicy.TENANT_SCOPED,
        proxy_prefix_format="/tenant/{tenant_id}/evidence-query/v1",
        requires_scope_parameter=True,
        forbid_methods=["DELETE", "PATCH"],
        required_fields=["openapi", "info.title", "info.version", "paths"],
        require_openapi_major="3.",
        enforce_version_alignment=True,
        inject_metadata=True,
        extension_namespace="x-governance",
    )

    # Step 2: Define a sample OpenAPI contract to validate.
    # This contract intentionally includes a forbidden DELETE method
    # to demonstrate how validation catches policy violations.
    contract = {
        "openapi": "3.0.3",
        "info": {
            "title": "Evidence Query API",
            "version": "1.2.0",
            "description": "API for querying evidence records",
        },
        "paths": {
            "/evidence": {
                "get": {
                    "summary": "List evidence records",
                    "operationId": "listEvidence",
                    "responses": {"200": {"description": "Success"}},
                },
                "post": {
                    "summary": "Create evidence record",
                    "operationId": "createEvidence",
                    "responses": {"201": {"description": "Created"}},
                },
                # This DELETE method violates the stipulation policy
                "delete": {
                    "summary": "Delete all evidence",
                    "operationId": "deleteAllEvidence",
                    "responses": {"204": {"description": "Deleted"}},
                },
            },
            "/evidence/{id}": {
                "get": {
                    "summary": "Get evidence by ID",
                    "operationId": "getEvidence",
                    "responses": {"200": {"description": "Success"}},
                },
            },
        },
    }

    # Step 3: Create the validation pipeline with the stipulation.
    # The pipeline automatically includes default validators for:
    # - OpenAPI version, required fields, forbidden methods,
    #   tenant scoping, and version alignment.
    pipeline = ValidationPipeline(stipulation)

    # Step 4: Run validation against the contract.
    result = pipeline.validate(contract)

    # Step 5: Inspect the validation result.
    print("=" * 60)
    print("CONTRACT VALIDATION RESULT")
    print("=" * 60)
    print(f"Valid: {result.is_valid}")
    print(f"Stipulation applied: {result.applied_stipulation}")
    print(f"Errors: {result.get_error_count()}")
    print(f"Warnings: {result.get_warning_count()}")

    # Step 6: Display any validation errors with details.
    if result.errors:
        print("\n--- Errors ---")
        for error in result.errors:
            print(f"  [{error.code}] {error.message}")
            if error.field_path:
                print(f"    Field: {error.field_path}")

    # Step 7: Display any validation warnings.
    if result.warnings:
        print("\n--- Warnings ---")
        for warning in result.warnings:
            print(f"  [{warning.code}] {warning.message}")

    # Step 8: Show the full summary as a dictionary (useful for logging).
    print("\n--- Summary Dict ---")
    summary = result.get_summary()
    for key, value in summary.items():
        print(f"  {key}: {value}")

    print("\n" + "=" * 60)

    # --- Bonus: Validate a compliant contract ---
    print("\nValidating a COMPLIANT contract (no forbidden methods)...")

    compliant_contract = {
        "openapi": "3.0.3",
        "info": {
            "title": "Evidence Query API",
            "version": "1.0.0",
        },
        "paths": {
            "/evidence": {
                "get": {
                    "summary": "List evidence",
                    "responses": {"200": {"description": "OK"}},
                },
            },
        },
    }

    compliant_result = pipeline.validate(compliant_contract)
    print(f"Valid: {compliant_result.is_valid}")
    print(f"Errors: {compliant_result.get_error_count()}")
    print(f"Warnings: {compliant_result.get_warning_count()}")


if __name__ == "__main__":
    main()
