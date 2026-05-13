"""
URL Template Resolver for Stipulation Server URLs.

Resolves ${VARIABLE} placeholders in server URL templates using environment variables.
"""

import os
import re
from typing import Dict, List


class UrlTemplateResolver:
    """
    Resolves URL templates with ${VARIABLE} placeholders.

    Follows Single Responsibility Principle - only handles URL template resolution.
    """

    @staticmethod
    def resolve_server_urls(server_urls: List[Dict[str, str]]) -> List[Dict[str, str]]:
        """
        Resolve server URL templates by substituting environment variables.

        Args:
            server_urls: List of server URL definitions with url_template fields

        Returns:
            List of server URLs with resolved 'url' fields

        Example:
            Input:  [{"name": "EXTERNAL", "url_template": "https://${PUBLIC_API_DOMAIN}", "description": "Public"}]
            Output: [{"url": "https://api.example.com", "description": "Public API endpoint"}]
        """
        resolved = []

        for server in server_urls:
            url_template = server.get('url_template', '')
            description = server.get('description', '')
            name = server.get('name', '')

            # Resolve template variables
            resolved_url = UrlTemplateResolver._resolve_template(url_template)

            # Build resolved server entry
            resolved_server = {
                'url': resolved_url,
                'description': description or f"{name} endpoint"
            }

            resolved.append(resolved_server)

        return resolved

    @staticmethod
    def _resolve_template(template: str) -> str:
        """
        Resolve ${VARIABLE} placeholders in template string.

        Args:
            template: Template string with ${VAR} placeholders

        Returns:
            Resolved string with environment variable values
        """
        def replace_var(match):
            """Substitute a matched ${VARIABLE} placeholder with its environment variable value."""
            var_name = match.group(1)
            value = os.getenv(var_name, '')
            if not value:
                raise ValueError(f"Environment variable ${{{var_name}}} not set")
            return value

        return re.sub(r'\$\{([A-Z_][A-Z0-9_]*)\}', replace_var, template)
