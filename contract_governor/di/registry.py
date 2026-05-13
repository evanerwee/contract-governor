"""
Service registry for managing service registrations and discovery.

Provides a centralized registry for service registrations with support
for service discovery, health checking, and lifecycle management.
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Type


class ServiceStatus(Enum):
    """Service status enumeration."""

    REGISTERED = "registered"
    ACTIVE = "active"
    INACTIVE = "inactive"
    ERROR = "error"


@dataclass
class ServiceRegistration:
    """Service registration information."""

    interface: Type
    implementation: Type
    name: Optional[str]
    scope: str
    status: ServiceStatus
    registered_at: datetime
    metadata: Dict[str, Any]
    health_check: Optional[Callable[[], bool]] = None


class ServiceRegistry:
    """
    Centralized registry for service registrations and discovery.

    Manages service registrations with metadata, health checking,
    and service discovery capabilities.
    """

    def __init__(self):
        """Initialize an empty service registry with registration and tag stores."""
        self._registrations: Dict[str, ServiceRegistration] = {}
        self._tags: Dict[str, List[str]] = {}  # tag -> service_keys

    def register_service(
        self,
        interface: Type,
        implementation: Type,
        name: Optional[str] = None,
        scope: str = "singleton",
        metadata: Optional[Dict[str, Any]] = None,
        tags: Optional[List[str]] = None,
        health_check: Optional[Callable[[], bool]] = None,
    ) -> str:
        """
        Register a service with the registry.

        Args:
            interface: Service interface
            implementation: Service implementation
            name: Optional service name
            scope: Service scope
            metadata: Optional service metadata
            tags: Optional service tags for discovery
            health_check: Optional health check function

        Returns:
            Service registration key
        """
        service_key = self._get_service_key(interface, name)

        registration = ServiceRegistration(
            interface=interface,
            implementation=implementation,
            name=name,
            scope=scope,
            status=ServiceStatus.REGISTERED,
            registered_at=datetime.now(timezone.utc),
            metadata=metadata or {},
            health_check=health_check,
        )

        self._registrations[service_key] = registration

        # Register tags
        if tags:
            for tag in tags:
                if tag not in self._tags:
                    self._tags[tag] = []
                self._tags[tag].append(service_key)

        return service_key

    def get_registration(self, interface: Type, name: Optional[str] = None) -> Optional[ServiceRegistration]:
        """
        Get service registration information.

        Args:
            interface: Service interface
            name: Optional service name

        Returns:
            Service registration if found, None otherwise
        """
        service_key = self._get_service_key(interface, name)
        return self._registrations.get(service_key)

    def find_services_by_tag(self, tag: str) -> List[ServiceRegistration]:
        """
        Find services by tag.

        Args:
            tag: Service tag

        Returns:
            List of service registrations with the tag
        """
        if tag not in self._tags:
            return []

        return [
            self._registrations[service_key] for service_key in self._tags[tag] if service_key in self._registrations
        ]

    def find_services_by_interface(self, interface: Type) -> List[ServiceRegistration]:
        """
        Find all services implementing an interface.

        Args:
            interface: Service interface

        Returns:
            List of service registrations implementing the interface
        """
        return [
            registration
            for registration in self._registrations.values()
            if issubclass(registration.implementation, interface)
        ]

    def update_service_status(self, interface: Type, name: Optional[str], status: ServiceStatus) -> bool:
        """
        Update service status.

        Args:
            interface: Service interface
            name: Optional service name
            status: New service status

        Returns:
            True if updated successfully, False if service not found
        """
        service_key = self._get_service_key(interface, name)

        if service_key in self._registrations:
            self._registrations[service_key].status = status
            return True

        return False

    def check_service_health(self, interface: Type, name: Optional[str] = None) -> bool:
        """
        Check service health using registered health check function.

        Args:
            interface: Service interface
            name: Optional service name

        Returns:
            True if healthy, False otherwise
        """
        registration = self.get_registration(interface, name)

        if not registration or not registration.health_check:
            return True  # Assume healthy if no health check

        try:
            is_healthy = registration.health_check()
            new_status = ServiceStatus.ACTIVE if is_healthy else ServiceStatus.INACTIVE
            self.update_service_status(interface, name, new_status)
            return is_healthy
        except Exception:
            self.update_service_status(interface, name, ServiceStatus.ERROR)
            return False

    def get_service_info(self) -> Dict[str, Any]:
        """
        Get information about all registered services.

        Returns:
            Dictionary with service registry information
        """
        return {
            "total_services": len(self._registrations),
            "services_by_status": {
                status.value: len([r for r in self._registrations.values() if r.status == status])
                for status in ServiceStatus
            },
            "available_tags": list(self._tags.keys()),
            "services": [
                {
                    "interface": f"{reg.interface.__module__}.{reg.interface.__name__}",
                    "implementation": f"{reg.implementation.__module__}.{reg.implementation.__name__}",
                    "name": reg.name,
                    "scope": reg.scope,
                    "status": reg.status.value,
                    "registered_at": reg.registered_at.isoformat(),
                    "metadata": reg.metadata,
                }
                for reg in self._registrations.values()
            ],
        }

    def unregister_service(self, interface: Type, name: Optional[str] = None) -> bool:
        """
        Unregister a service.

        Args:
            interface: Service interface
            name: Optional service name

        Returns:
            True if unregistered successfully, False if service not found
        """
        service_key = self._get_service_key(interface, name)

        if service_key in self._registrations:
            # Remove from tags
            for tag_services in self._tags.values():
                if service_key in tag_services:
                    tag_services.remove(service_key)

            # Remove registration
            del self._registrations[service_key]
            return True

        return False

    def clear(self) -> None:
        """Clear all service registrations."""
        self._registrations.clear()
        self._tags.clear()

    def _get_service_key(self, interface: Type, name: Optional[str]) -> str:
        """Generate a unique key for the service."""
        base_key = f"{interface.__module__}.{interface.__name__}"
        return f"{base_key}:{name}" if name else base_key
