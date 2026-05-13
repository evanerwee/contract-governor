"""
Example: Transforming an OpenAPI contract for controlled exposure.

This example demonstrates how to use contract-governor's TransformationPipeline
to transform a raw backend contract into a safe, governed version suitable
for client consumption.

The transformation pipeline applies:
- URL rewriting (internal URLs → proxy gateway URLs)
- Method stripping (removes forbidden HTTP methods from paths)
- Audit metadata injection (adds governance tracking info)
"""

from contract_governor.core.models import (
    ExposurePolicy,
    StipulationConfig,
    TransformContext,
)
from contract_governor.transformation import TransformationPipeline


def main():
    # Step 1: Define the stipulation policy governing this contract.
    # The policy specifies which methods to strip, how URLs should be
    # rewritten, and what metadata to inject.
    stipulation = StipulationConfig(
        stipulation_id="evidence-query-v1-policy",
        exposure_policy=ExposurePolicy.TENANT_SCOPED,
        proxy_prefix_format="/tenant/{tenant_id}/evidence-query/v1",
        requires_scope_parameter=True,
        forbid_methods=["DELETE", "PATCH"],
        required_fields=["openapi", "info.title", "info.version", "paths"],
        require_openapi_major="3.",
        inject_metadata=True,
        extension_namespace="x-governance",
        metadata_block={
            "audit_note": "Governed by evidence-query-v1 stipulation",
            "data_classification": "internal",
        },
    )

    # Step 2: Define the raw OpenAPI contract from the backend service.
    # This contract has internal server URLs and includes methods that
    # should not be exposed to external consumers.
    raw_contract = {
        "openapi": "3.0.3",
        "info": {
            "title": "Evidence Query API",
            "version": "1.2.0",
            "description": "Internal evidence query service",
        },
        "servers": [
            {
                "url": "http://evidence-service.internal:8080",
                "description": "Internal backend service",
            }
        ],
        "paths": {
            "/evidence": {
                "get": {
                    "summary": "List evidence records",
                    "operationId": "listEvidence",
                    "parameters": [
                        {
                            "name": "limit",
                            "in": "query",
                            "schema": {"type": "integer", "default": 50},
                        }
                    ],
                    "responses": {"200": {"description": "List of evidence records"}},
                },
                "post": {
                    "summary": "Create evidence record",
                    "operationId": "createEvidence",
                    "responses": {"201": {"description": "Created"}},
                },
                # DELETE is forbidden by the stipulation — will be stripped
                "delete": {
                    "summary": "Delete all evidence (admin only)",
                    "operationId": "deleteAllEvidence",
                    "responses": {"204": {"description": "Deleted"}},
                },
            },
            "/evidence/{id}": {
                "get": {
                    "summary": "Get evidence by ID",
                    "operationId": "getEvidence",
                    "responses": {"200": {"description": "Evidence record"}},
                },
                # PATCH is forbidden by the stipulation — will be stripped
                "patch": {
                    "summary": "Partially update evidence",
                    "operationId": "patchEvidence",
                    "responses": {"200": {"description": "Updated"}},
                },
            },
        },
    }

    # Step 3: Create the transformation context.
    # This provides the pipeline with routing info, scope parameters,
    # and the gateway URL for URL rewriting.
    context = TransformContext(
        category="evidence-query",
        api_major_version="v1",
        contract_version="1.2.0",
        gateway_base_url="https://api.example.com",
        scope_parameters={"tenant_id": "acme-corp"},
        target_audience="public",
        source_service="evidence-service",
        environment="production",
    )

    # Step 4: Create the transformation pipeline.
    # The pipeline automatically sets up the default transformer chain:
    #   URLRewriter → MethodStripper → AuditMetadataInjector
    pipeline = TransformationPipeline(stipulation)

    # Step 5: Preview what the transformation will do (optional).
    print("=" * 60)
    print("TRANSFORMATION PREVIEW")
    print("=" * 60)
    preview = pipeline.preview_transformation(raw_contract, context)
    print(f"Stipulation: {preview['stipulation_id']}")
    for key, value in preview.get("estimated_changes", {}).items():
        print(f"  {key}: {value}")

    # Step 6: Execute the transformation.
    transformed_contract = pipeline.transform(raw_contract, context)

    # Step 7: Inspect the transformed output.
    print("\n" + "=" * 60)
    print("TRANSFORMATION RESULT")
    print("=" * 60)

    # Show that servers have been rewritten from internal to proxy URLs
    print("\n--- Servers (rewritten) ---")
    for server in transformed_contract.get("servers", []):
        print(f"  URL: {server.get('url', 'N/A')}")
        print(f"  Description: {server.get('description', 'N/A')}")

    # Show which paths and methods remain after stripping
    print("\n--- Paths (after method stripping) ---")
    for path, methods in transformed_contract.get("paths", {}).items():
        if isinstance(methods, dict):
            remaining_methods = [
                m.upper() for m in methods.keys() if m != "parameters"
            ]
            print(f"  {path}: {', '.join(remaining_methods)}")

    # Show injected governance metadata
    print("\n--- Governance Metadata (injected) ---")
    governance = transformed_contract.get("x-governance", {})
    if governance:
        for key, value in governance.items():
            print(f"  {key}: {value}")
    else:
        print("  (metadata injected under x-transformation-metadata)")
        meta = transformed_contract.get("x-transformation-metadata", {})
        for key, value in meta.items():
            print(f"  {key}: {value}")

    # Step 8: Show the full list of transformers that were applied.
    print("\n--- Transformers Applied ---")
    for info in pipeline.get_transformer_info():
        print(f"  {info['name']}: {info['description']}")

    print("\n" + "=" * 60)


if __name__ == "__main__":
    main()
