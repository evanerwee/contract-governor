"""
Centralized contract categorization logic.

This module provides utilities for detecting the category and API version
of OpenAPI contracts based on file path conventions and directory structure.
"""

from pathlib import Path
from typing import Optional


class ContractCategorizer:
    """Centralized logic for categorizing OpenAPI contracts."""

    @staticmethod
    def detect_category(file_path: Path) -> Optional[str]:
        """
        Detect contract category based on filename and directory structure.

        This is the single source of truth for contract categorization
        used by both S3 publish scripts and runtime loading.

        Args:
            file_path: Path to the contract file

        Returns:
            Category string or None if not categorizable
        """
        filename = file_path.name.lower()
        parent_dir = file_path.parent.name.lower()
        grandparent_dir = file_path.parent.parent.name.lower() if len(file_path.parent.parts) > 1 else None

        # Use directory name as primary category indicator
        if parent_dir in [
            "authentication",
            "authorization",
            "dataplane",
            "factory",
            "registration",
            "telemetry",
            "subscription",
        ]:
            return parent_dir

        # Check grandparent directory for versioned contracts (e.g., dataplane/v1.0.0/file.yaml)
        if grandparent_dir and grandparent_dir in [
            "authentication",
            "authorization",
            "dataplane",
            "factory",
            "registration",
            "telemetry",
            "subscription",
        ]:
            return grandparent_dir

        # For files in core directory, detect by filename
        if parent_dir == "core":
            return ContractCategorizer._categorize_core_file(filename)

        return None

    @staticmethod
    def _categorize_core_file(filename: str) -> Optional[str]:
        """Categorize files in the core directory by filename patterns."""

        # Authentication
        if "authentication" in filename or "mtls" in filename:
            return "authentication"

        # Authorization (broad category for all auth-related services)
        authz_keywords = ["entitlement", "authorization", "policy", "opa", "spicedb"]
        if any(keyword in filename for keyword in authz_keywords):
            return "authorization"

        # Factory (broad category for all factory/registration services)
        if "factory" in filename or "registration" in filename:
            return "factory"

        # User enrollment
        if "user" in filename and "enrollment" in filename:
            return "enrollment"

        # Telemetry
        if "telemetry" in filename:
            return "telemetry"

        # Subscription
        if "subscription" in filename:
            return "subscription"

        # Decision router
        if "decision" in filename or "router" in filename:
            return "decision-router"

        # Prompts
        if "prompt" in filename:
            return "prompts"

        # Security context
        if "security" in filename and "context" in filename:
            return "security_context"

        return None
