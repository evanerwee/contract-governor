"""
Contract Governor Extensions.

This module provides framework-specific extensions that integrate contract-governor
capabilities into web frameworks such as FastAPI with minimal configuration.
"""
from .fastapi_extension import ContractGovernorFastAPIExtension

__all__ = ["ContractGovernorFastAPIExtension"]
