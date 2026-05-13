"""
Example demonstrating contract-stipulation linking.

Shows how contracts are automatically linked to stipulations based on
category and version naming conventions.
"""

from contract_governor.config import LocalFileConfigSource
from contract_governor.core import Manifest, StipulationLinker
from contract_governor.loaders import ContractLoader


def main():
    # Setup configuration source pointing to local stipulation files
    config_source = LocalFileConfigSource("config/stipulations")

    # Create stipulation linker — links contracts to stipulations by path convention
    linker = StipulationLinker(config_source)

    # Create contract loader (uses linker to find stipulations for loaded contracts)
    loader = ContractLoader(linker)

    # Example: Find a stipulation for a contract path
    contract_path = "contracts/evidence-query/v1/openapi.yaml"

    print(f"Looking up stipulation for: {contract_path}")

    # Find stipulation for this contract based on path convention
    stipulation = linker.find_stipulation_by_path(contract_path)

    if stipulation:
        print(f"✓ Found stipulation: {stipulation.stipulation_id}")
        print(f"  Exposure policy: {stipulation.exposure_policy}")
        print(f"  Proxy prefix: {stipulation.proxy_prefix_format}")
        print(f"  Forbidden methods: {stipulation.forbid_methods}")
    else:
        print("✗ No stipulation found (expected if no config files exist)")

    # Example: Generate a manifest linking contracts to stipulations
    print("\nGenerating manifest...")
    manifest = Manifest()

    # Add a contract-stipulation link to the manifest
    manifest.add_contract(
        path="contracts/evidence-query/v1/openapi.yaml",
        category="evidence-query",
        version="v1",
        stipulation_path="stipulations/evidence-query_v1.yaml",
        content=b"dummy contract content",
    )

    manifest.add_stipulation(
        path="stipulations/evidence-query_v1.yaml",
        category="evidence-query",
        version="v1",
        content=b"dummy stipulation content",
    )

    print("Manifest links:")
    for link in manifest.links:
        print(f"  {link.contract} → {link.stipulation}")

    # Show manifest as dictionary (useful for serialization)
    print("\nManifest dict:")
    manifest_dict = manifest.to_dict()
    print(f"  Contracts: {len(manifest_dict['contracts'])}")
    print(f"  Stipulations: {len(manifest_dict['stipulations'])}")
    print(f"  Links: {len(manifest_dict['links'])}")

    # Note: ContractLoader.load_contract() requires an actual OpenAPI file on disk.
    # In a real scenario you would use it like:
    #   contract, stipulation = loader.load_contract("path/to/openapi.yaml")
    print(f"\nContractLoader ready: {loader is not None}")


if __name__ == "__main__":
    main()
