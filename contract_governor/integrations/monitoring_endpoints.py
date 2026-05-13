"""
Monitoring and metrics endpoints for FastAPI integration.

This module provides HTTP endpoints for accessing monitoring data,
metrics, and audit logs from the Contract Stipulations system.
"""

from datetime import datetime, timedelta, timezone
from typing import Any, Optional

try:
    from fastapi import FastAPI, HTTPException, Query
    from fastapi.responses import JSONResponse
except ImportError:
    raise ImportError("FastAPI is required for this module. " "Install with: pip install contract-governor[server]")

from ..core.monitoring import get_global_audit_logger, get_global_metrics_collector, get_global_performance_monitor


class MonitoringEndpoints:
    """
    FastAPI endpoints for monitoring and observability.
    """

    def __init__(self, app: FastAPI):
        """
        Initialize monitoring endpoints.

        Args:
            app: FastAPI application instance
        """
        self.app = app
        self.metrics_collector = get_global_metrics_collector()
        self.audit_logger = get_global_audit_logger()
        self.performance_monitor = get_global_performance_monitor()

    def register_endpoints(self, prefix: str = "/monitoring") -> None:
        """
        Register all monitoring endpoints with the FastAPI app.

        Args:
            prefix: URL prefix for monitoring endpoints
        """

        @self.app.get(f"{prefix}/health", response_class=JSONResponse)
        async def monitoring_health():
            """Get monitoring system health status."""
            try:
                return {
                    "status": "healthy",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "components": {
                        "metrics_collector": "healthy",
                        "audit_logger": "healthy",
                        "performance_monitor": "healthy",
                    },
                }
            except Exception as e:
                raise HTTPException(status_code=503, detail=f"Monitoring system unhealthy: {str(e)}")

        @self.app.get(f"{prefix}/metrics", response_class=JSONResponse)
        async def get_metrics(
            limit: int = Query(100, description="Maximum number of recent metrics to return"),
            metric_type: Optional[str] = Query(None, description="Filter by metric type"),
        ):
            """Get recent metrics data."""
            try:
                if self.metrics_collector is None:
                    raise HTTPException(status_code=503, detail="Metrics collector not initialized")
                recent_metrics = self.metrics_collector.get_recent_metrics(limit)

                # Filter by metric type if specified
                if metric_type:
                    recent_metrics = [m for m in recent_metrics if m.get("type") == metric_type]

                return {
                    "metrics": recent_metrics,
                    "total": len(recent_metrics),
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"Failed to retrieve metrics: {str(e)}")

        @self.app.get(f"{prefix}/metrics/summary", response_class=JSONResponse)
        async def get_metrics_summary():
            """Get summary of all current metrics."""
            try:
                summary = self.metrics_collector.get_all_metrics_summary()
                return {"summary": summary, "timestamp": datetime.now(timezone.utc).isoformat()}
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"Failed to retrieve metrics summary: {str(e)}")

        @self.app.get(f"{prefix}/audit", response_class=JSONResponse)
        async def get_audit_events(
            limit: int = Query(100, description="Maximum number of recent events to return"),
            event_type: Optional[str] = Query(None, description="Filter by event type"),
            contract_category: Optional[str] = Query(None, description="Filter by contract category"),
            success_only: Optional[bool] = Query(None, description="Filter by success status"),
        ):
            """Get recent audit events."""
            try:
                if self.audit_logger is None:
                    raise HTTPException(status_code=503, detail="Audit logger not initialized")
                events = self.audit_logger.get_recent_events(limit)

                # Apply filters
                if event_type:
                    events = [e for e in events if e.get("event_type") == event_type]

                if contract_category:
                    events = [e for e in events if e.get("contract_category") == contract_category]

                if success_only is not None:
                    events = [e for e in events if e.get("success") == success_only]

                return {"events": events, "total": len(events), "timestamp": datetime.now(timezone.utc).isoformat()}
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"Failed to retrieve audit events: {str(e)}")

        @self.app.get(f"{prefix}/performance", response_class=JSONResponse)
        async def get_performance_stats(
            operation_type: Optional[str] = Query(None, description="Filter by operation type"),
            contract_category: Optional[str] = Query(None, description="Filter by contract category"),
            time_window_hours: int = Query(24, description="Time window in hours for statistics"),
        ):
            """Get performance statistics."""
            try:
                if self.metrics_collector is None:
                    raise HTTPException(status_code=503, detail="Metrics collector not initialized")
                # Get recent metrics for performance analysis
                recent_metrics = self.metrics_collector.get_recent_metrics(1000)

                # Filter by time window
                cutoff_time = datetime.now(timezone.utc) - timedelta(hours=time_window_hours)
                recent_metrics = [
                    m
                    for m in recent_metrics
                    if datetime.fromisoformat(m["timestamp"].replace("Z", "+00:00")) > cutoff_time
                ]

                # Apply filters
                if operation_type:
                    recent_metrics = [
                        m for m in recent_metrics if m.get("labels", {}).get("operation") == operation_type
                    ]

                if contract_category:
                    recent_metrics = [
                        m for m in recent_metrics if m.get("labels", {}).get("category") == contract_category
                    ]

                # Calculate statistics
                operation_counts: dict[str, Any] = {}
                duration_stats: dict[str, Any] = {}
                error_rates: dict[str, Any] = {}

                for metric in recent_metrics:
                    labels = metric.get("labels", {})
                    operation = labels.get("operation", "unknown")

                    if metric["name"].endswith("_total"):
                        operation_counts[operation] = operation_counts.get(operation, 0) + metric["value"]

                    if metric["name"].endswith("_duration_seconds"):
                        if operation not in duration_stats:
                            duration_stats[operation] = []
                        duration_stats[operation].append(metric["value"])

                # Calculate duration percentiles
                for operation, durations in duration_stats.items():
                    if durations:
                        sorted_durations = sorted(durations)
                        count = len(sorted_durations)
                        duration_stats[operation] = {
                            "count": count,
                            "min": sorted_durations[0],
                            "max": sorted_durations[-1],
                            "mean": sum(sorted_durations) / count,
                            "p50": sorted_durations[int(count * 0.5)],
                            "p90": sorted_durations[int(count * 0.9)],
                            "p95": sorted_durations[int(count * 0.95)],
                            "p99": sorted_durations[int(count * 0.99)],
                        }

                return {
                    "time_window_hours": time_window_hours,
                    "operation_counts": operation_counts,
                    "duration_statistics": duration_stats,
                    "error_rates": error_rates,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"Failed to retrieve performance stats: {str(e)}")

        @self.app.get(f"{prefix}/errors", response_class=JSONResponse)
        async def get_error_summary(
            time_window_hours: int = Query(24, description="Time window in hours for error analysis"),
            contract_category: Optional[str] = Query(None, description="Filter by contract category"),
        ):
            """Get error summary and rates."""
            try:
                if self.audit_logger is None:
                    raise HTTPException(status_code=503, detail="Audit logger not initialized")
                # Get recent audit events for error analysis
                events = self.audit_logger.get_recent_events(1000)

                # Filter by time window
                cutoff_time = datetime.now(timezone.utc) - timedelta(hours=time_window_hours)
                recent_events = [
                    e for e in events if datetime.fromisoformat(e["timestamp"].replace("Z", "+00:00")) > cutoff_time
                ]

                # Apply category filter
                if contract_category:
                    recent_events = [e for e in recent_events if e.get("contract_category") == contract_category]

                # Calculate error statistics
                total_events = len(recent_events)
                failed_events = [e for e in recent_events if not e.get("success", True)]
                error_rate = len(failed_events) / total_events if total_events > 0 else 0

                # Group errors by type and category
                error_by_type: dict[str, int] = {}
                error_by_category: dict[str, int] = {}
                error_by_operation: dict[str, int] = {}

                for event in failed_events:
                    error_code = event.get("error_code", "unknown")
                    category = event.get("contract_category", "unknown")
                    operation = event.get("operation", "unknown")

                    error_by_type[error_code] = error_by_type.get(error_code, 0) + 1
                    error_by_category[category] = error_by_category.get(category, 0) + 1
                    error_by_operation[operation] = error_by_operation.get(operation, 0) + 1

                return {
                    "time_window_hours": time_window_hours,
                    "total_events": total_events,
                    "failed_events": len(failed_events),
                    "error_rate": error_rate,
                    "errors_by_type": error_by_type,
                    "errors_by_category": error_by_category,
                    "errors_by_operation": error_by_operation,
                    "recent_errors": failed_events[-10:],  # Last 10 errors
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"Failed to retrieve error summary: {str(e)}")

        @self.app.get(f"{prefix}/contracts/stats", response_class=JSONResponse)
        async def get_contract_stats():
            """Get contract-specific statistics."""
            try:
                # Get recent audit events for contract analysis
                events = self.audit_logger.get_recent_events(1000)

                # Analyze contract exposure and access patterns
                exposure_events = [e for e in events if e.get("event_type") == "contract_exposure"]
                access_events = [e for e in events if e.get("event_type") == "contract_access"]

                # Count by category and version
                categories = {}
                versions = {}

                for event in exposure_events + access_events:
                    category = event.get("contract_category", "unknown")
                    version = event.get("api_major_version", "unknown")

                    categories[category] = categories.get(category, 0) + 1
                    versions[version] = versions.get(version, 0) + 1

                return {
                    "total_exposures": len(exposure_events),
                    "total_accesses": len(access_events),
                    "contracts_by_category": categories,
                    "contracts_by_version": versions,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"Failed to retrieve contract stats: {str(e)}")


def register_monitoring_endpoints(app: FastAPI, prefix: str = "/monitoring") -> None:
    """
    Register monitoring endpoints with a FastAPI application.

    Args:
        app: FastAPI application instance
        prefix: URL prefix for monitoring endpoints
    """
    monitoring = MonitoringEndpoints(app)
    monitoring.register_endpoints(prefix)
