"""
Contract loaders for various sources.

This module provides contract loading implementations that read OpenAPI
specifications from local files, S3, and other backends with automatic
stipulation linking.
"""

from .contract_loader import ContractLoader

__all__ = ["ContractLoader"]
