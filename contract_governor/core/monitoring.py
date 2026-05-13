"""
Monitoring and observability system for Contract Stipulations.

This module provides comprehensive metrics collection, performance monitoring,
and audit logging for contract validation, transformation, and exposure operations.
"""

import logging
import threading
import time
from collections import defaultdict, deque
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from functools import wraps
from typing import Any, Callable, Dict, List, Optional


class MetricType(Enum):
    """Types of metrics collected by the monitoring system."""

    COUNTER = "counter"
    GAUGE = "gauge"
    HISTOGRAM = "histogram"
    TIMER = "timer"


class OperationType(Enum):
    """Types of operations monitored by the system."""

    VALIDATION = "validation"
    TRANSFORMATION = "transformation"
    CONTRACT_EXPOSURE = "contract_exposure"
    CONTRACT_RETRIEVAL = "contract_retrieval"
    CATALOG_GENERATION = "catalog_generation"
    CONFIGURATION_LOAD = "configuration_load"


@dataclass
class MetricPoint:
    """A single metric data point."""

    name: str
    value: float
    metric_type: MetricType
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    labels: Dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert metric point to dictionary."""
        return {
            "name": self.name,
            "value": self.value,
            "type": self.metric_type.value,
            "timestamp": self.timestamp.isoformat(),
            "labels": self.labels,
        }


@dataclass
class PerformanceMetrics:
    """Performance metrics for an operation."""

    operation_type: OperationType
    duration_seconds: float
    success: bool
    error_code: Optional[str] = None
    contract_category: Optional[str] = None
    api_major_version: Optional[str] = None
    stipulation_id: Optional[str] = None
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> Dict[str, Any]:
        """Convert performance metrics to dictionary."""
        return {
            "operation_type": self.operation_type.value,
            "duration_seconds": self.duration_seconds,
            "success": self.success,
            "error_code": self.error_code,
            "contract_category": self.contract_category,
            "api_major_version": self.api_major_version,
            "stipulation_id": self.stipulation_id,
            "timestamp": self.timestamp.isoformat(),
        }


@dataclass
class AuditEvent:
    """Audit event for contract exposure and access."""

    event_type: str
    contract_category: str
    api_major_version: str
    operation: str
    success: bool
    user_id: Optional[str] = None
    client_ip: Optional[str] = None
    user_agent: Optional[str] = None
    request_id: Optional[str] = None
    stipulation_id: Optional[str] = None
    error_code: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> Dict[str, Any]:
        """Convert audit event to dictionary."""
        return {
            "event_type": self.event_type,
            "contract_category": self.contract_category,
            "api_major_version": self.api_major_version,
            "operation": self.operation,
            "success": self.success,
            "user_id": self.user_id,
            "client_ip": self.client_ip,
            "user_agent": self.user_agent,
            "request_id": self.request_id,
            "stipulation_id": self.stipulation_id,
            "error_code": self.error_code,
            "metadata": self.metadata,
            "timestamp": self.timestamp.isoformat(),
        }


class MetricsCollector:
    """
    Thread-safe metrics collector for performance and operational metrics.
    """

    def __init__(self, max_history: int = 10000):
        """
        Initialize metrics collector.

        Args:
            max_history: Maximum number of metric points to keep in memory
        """
        self.max_history = max_history
        self._metrics: deque = deque(maxlen=max_history)
        self._counters: Dict[str, float] = defaultdict(float)
        self._gauges: Dict[str, float] = {}
        self._histograms: Dict[str, List[float]] = defaultdict(list)
        self._lock = threading.RLock()

    def increment_counter(self, name: str, value: float = 1.0, labels: Optional[Dict[str, str]] = None) -> None:
        """Increment a counter metric."""
        with self._lock:
            key = self._make_key(name, labels)
            self._counters[key] += value

            metric = MetricPoint(
                name=name, value=self._counters[key], metric_type=MetricType.COUNTER, labels=labels or {}
            )
            self._metrics.append(metric)

    def set_gauge(self, name: str, value: float, labels: Optional[Dict[str, str]] = None) -> None:
        """Set a gauge metric value."""
        with self._lock:
            key = self._make_key(name, labels)
            self._gauges[key] = value

            metric = MetricPoint(name=name, value=value, metric_type=MetricType.GAUGE, labels=labels or {})
            self._metrics.append(metric)

    def record_histogram(self, name: str, value: float, labels: Optional[Dict[str, str]] = None) -> None:
        """Record a value in a histogram metric."""
        with self._lock:
            key = self._make_key(name, labels)
            self._histograms[key].append(value)

            # Keep only recent values to prevent memory growth
            if len(self._histograms[key]) > 1000:
                self._histograms[key] = self._histograms[key][-1000:]

            metric = MetricPoint(name=name, value=value, metric_type=MetricType.HISTOGRAM, labels=labels or {})
            self._metrics.append(metric)

    def record_timer(self, name: str, duration: float, labels: Optional[Dict[str, str]] = None) -> None:
        """Record a timer metric (duration in seconds)."""
        with self._lock:
            metric = MetricPoint(name=name, value=duration, metric_type=MetricType.TIMER, labels=labels or {})
            self._metrics.append(metric)

            # Also record as histogram for percentile calculations
            self.record_histogram(f"{name}_duration", duration, labels)

    def get_counter(self, name: str, labels: Optional[Dict[str, str]] = None) -> float:
        """Get current counter value."""
        with self._lock:
            key = self._make_key(name, labels)
            return self._counters.get(key, 0.0)

    def get_gauge(self, name: str, labels: Optional[Dict[str, str]] = None) -> Optional[float]:
        """Get current gauge value."""
        with self._lock:
            key = self._make_key(name, labels)
            return self._gauges.get(key)

    def get_histogram_stats(self, name: str, labels: Optional[Dict[str, str]] = None) -> Dict[str, float]:
        """Get histogram statistics (min, max, mean, percentiles)."""
        with self._lock:
            key = self._make_key(name, labels)
            values = self._histograms.get(key, [])

            if not values:
                return {}

            sorted_values = sorted(values)
            count = len(sorted_values)

            return {
                "count": count,
                "min": sorted_values[0],
                "max": sorted_values[-1],
                "mean": sum(sorted_values) / count,
                "p50": sorted_values[int(count * 0.5)],
                "p90": sorted_values[int(count * 0.9)],
                "p95": sorted_values[int(count * 0.95)],
                "p99": sorted_values[int(count * 0.99)],
            }

    def get_recent_metrics(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Get recent metrics as dictionaries."""
        with self._lock:
            recent = list(self._metrics)[-limit:]
            return [metric.to_dict() for metric in recent]

    def get_all_metrics_summary(self) -> Dict[str, Any]:
        """Get summary of all current metrics."""
        with self._lock:
            return {
                "counters": dict(self._counters),
                "gauges": dict(self._gauges),
                "histogram_stats": {
                    name: self.get_histogram_stats(
                        name.split("|")[0], self._parse_labels(name.split("|")[1]) if "|" in name else None
                    )
                    for name in self._histograms.keys()
                },
                "total_metrics_collected": len(self._metrics),
            }

    def _make_key(self, name: str, labels: Optional[Dict[str, str]]) -> str:
        """Create a unique key for a metric with labels."""
        if not labels:
            return name

        label_str = ",".join(f"{k}={v}" for k, v in sorted(labels.items()))
        return f"{name}|{label_str}"

    def _parse_labels(self, label_str: str) -> Dict[str, str]:
        """Parse labels from string format."""
        if not label_str:
            return {}

        labels = {}
        for pair in label_str.split(","):
            if "=" in pair:
                k, v = pair.split("=", 1)
                labels[k] = v
        return labels


class AuditLogger:
    """
    Audit logger for contract exposure and access events.
    """

    def __init__(self, logger_name: str = "contract_stipulations.audit"):
        """
        Initialize audit logger.

        Args:
            logger_name: Name of the logger to use
        """
        self.logger = logging.getLogger(logger_name)
        self._events: deque = deque(maxlen=10000)
        self._lock = threading.RLock()

    def log_contract_exposure(
        self,
        contract_category: str,
        api_major_version: str,
        stipulation_id: str,
        success: bool,
        user_id: Optional[str] = None,
        request_id: Optional[str] = None,
        error_code: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Log contract exposure event."""
        event = AuditEvent(
            event_type="contract_exposure",
            contract_category=contract_category,
            api_major_version=api_major_version,
            operation="expose_contract",
            success=success,
            user_id=user_id,
            request_id=request_id,
            stipulation_id=stipulation_id,
            error_code=error_code,
            metadata=metadata or {},
        )

        self._log_event(event)

    def log_contract_access(
        self,
        contract_category: str,
        api_major_version: str,
        operation: str,
        success: bool,
        user_id: Optional[str] = None,
        client_ip: Optional[str] = None,
        user_agent: Optional[str] = None,
        request_id: Optional[str] = None,
        error_code: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Log contract access event."""
        event = AuditEvent(
            event_type="contract_access",
            contract_category=contract_category,
            api_major_version=api_major_version,
            operation=operation,
            success=success,
            user_id=user_id,
            client_ip=client_ip,
            user_agent=user_agent,
            request_id=request_id,
            error_code=error_code,
            metadata=metadata or {},
        )

        self._log_event(event)

    def log_catalog_access(
        self,
        operation: str,
        success: bool,
        contract_count: int,
        user_id: Optional[str] = None,
        client_ip: Optional[str] = None,
        user_agent: Optional[str] = None,
        request_id: Optional[str] = None,
        filters: Optional[Dict[str, Any]] = None,
        error_code: Optional[str] = None,
    ) -> None:
        """Log catalog access event."""
        event = AuditEvent(
            event_type="catalog_access",
            contract_category="catalog",
            api_major_version="all",
            operation=operation,
            success=success,
            user_id=user_id,
            client_ip=client_ip,
            user_agent=user_agent,
            request_id=request_id,
            error_code=error_code,
            metadata={"contract_count": contract_count, "filters": filters or {}},
        )

        self._log_event(event)

    def get_recent_events(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Get recent audit events."""
        with self._lock:
            recent = list(self._events)[-limit:]
            return [event.to_dict() for event in recent]

    def _log_event(self, event: AuditEvent) -> None:
        """Log an audit event."""
        with self._lock:
            self._events.append(event)

            # Log to standard logger
            self.logger.info(
                f"AUDIT: {event.event_type} - {event.operation} - "
                f"{event.contract_category}:{event.api_major_version} - "
                f"{'SUCCESS' if event.success else 'FAILED'}",
                extra=event.to_dict(),
            )


class PerformanceMonitor:
    """
    Performance monitor for tracking operation durations and success rates.
    """

    def __init__(self, metrics_collector: MetricsCollector):
        """
        Initialize performance monitor.

        Args:
            metrics_collector: MetricsCollector instance to use
        """
        self.metrics = metrics_collector

    @contextmanager
    def monitor_operation(
        self,
        operation_type: OperationType,
        contract_category: Optional[str] = None,
        api_major_version: Optional[str] = None,
        stipulation_id: Optional[str] = None,
    ):
        """
        Context manager for monitoring operation performance.

        Usage:
            with monitor.monitor_operation(OperationType.VALIDATION, "evidence-query", "v1"):
                # perform validation
                pass
        """
        start_time = time.time()
        success = True
        error_code = None

        # Create labels for metrics
        labels = {
            "operation": operation_type.value,
            "category": contract_category or "unknown",
            "api_major": api_major_version or "unknown",
        }

        if stipulation_id:
            labels["stipulation"] = stipulation_id

        try:
            # Increment operation start counter
            self.metrics.increment_counter("operations_started_total", labels=labels)

            yield

        except Exception as e:
            success = False
            error_code = getattr(e, "error_code", type(e).__name__)

            # Increment error counter
            error_labels = labels.copy()
            error_labels["error_code"] = error_code
            self.metrics.increment_counter("operations_failed_total", labels=error_labels)

            raise

        finally:
            # Record duration
            duration = time.time() - start_time
            self.metrics.record_timer("operation_duration_seconds", duration, labels)

            # Increment success/failure counters
            if success:
                self.metrics.increment_counter("operations_succeeded_total", labels=labels)

            # Record performance metrics
            PerformanceMetrics(
                operation_type=operation_type,
                duration_seconds=duration,
                success=success,
                error_code=error_code,
                contract_category=contract_category,
                api_major_version=api_major_version,
                stipulation_id=stipulation_id,
            )

    def record_validation_metrics(
        self,
        contract_category: str,
        api_major_version: str,
        stipulation_id: str,
        validation_duration: float,
        validation_errors: int,
        validation_warnings: int,
        success: bool,
    ) -> None:
        """Record detailed validation metrics."""
        labels = {"category": contract_category, "api_major": api_major_version, "stipulation": stipulation_id}

        self.metrics.record_timer("validation_duration_seconds", validation_duration, labels)
        self.metrics.record_histogram("validation_errors_count", validation_errors, labels)
        self.metrics.record_histogram("validation_warnings_count", validation_warnings, labels)

        if success:
            self.metrics.increment_counter("validations_passed_total", labels=labels)
        else:
            self.metrics.increment_counter("validations_failed_total", labels=labels)

    def record_transformation_metrics(
        self,
        contract_category: str,
        api_major_version: str,
        stipulation_id: str,
        transformation_duration: float,
        transformers_applied: int,
        success: bool,
    ) -> None:
        """Record detailed transformation metrics."""
        labels = {"category": contract_category, "api_major": api_major_version, "stipulation": stipulation_id}

        self.metrics.record_timer("transformation_duration_seconds", transformation_duration, labels)
        self.metrics.record_histogram("transformers_applied_count", transformers_applied, labels)

        if success:
            self.metrics.increment_counter("transformations_passed_total", labels=labels)
        else:
            self.metrics.increment_counter("transformations_failed_total", labels=labels)


def monitor_performance(operation_type: OperationType, metrics_collector: Optional[MetricsCollector] = None):
    """
    Decorator for monitoring function performance.

    Args:
        operation_type: Type of operation being monitored
        metrics_collector: Optional metrics collector (uses global if not provided)
    """

    def decorator(func: Callable) -> Callable:
        """Wrap a function with performance monitoring instrumentation."""

        @wraps(func)
        def wrapper(*args, **kwargs):
            """Execute the wrapped function while recording performance metrics."""
            # Use global metrics collector if not provided
            collector = metrics_collector or get_global_metrics_collector()
            monitor = PerformanceMonitor(collector)

            # Extract context from function arguments if available
            contract_category = kwargs.get("category") or kwargs.get("contract_category")
            api_major_version = kwargs.get("api_major") or kwargs.get("api_major_version")
            stipulation_id = kwargs.get("stipulation_id")

            with monitor.monitor_operation(
                operation_type=operation_type,
                contract_category=contract_category,
                api_major_version=api_major_version,
                stipulation_id=stipulation_id,
            ):
                return func(*args, **kwargs)

        return wrapper

    return decorator


# Global instances
_global_metrics_collector: Optional[MetricsCollector] = None
_global_audit_logger: Optional[AuditLogger] = None
_global_performance_monitor: Optional[PerformanceMonitor] = None


def initialize_monitoring(
    metrics_collector: Optional[MetricsCollector] = None, audit_logger: Optional[AuditLogger] = None
) -> None:
    """Initialize global monitoring instances."""
    global _global_metrics_collector, _global_audit_logger, _global_performance_monitor

    _global_metrics_collector = metrics_collector or MetricsCollector()
    _global_audit_logger = audit_logger or AuditLogger()
    _global_performance_monitor = PerformanceMonitor(_global_metrics_collector)


def get_global_metrics_collector() -> MetricsCollector | None:
    """Get the global metrics collector instance."""
    if _global_metrics_collector is None:
        initialize_monitoring()
    return _global_metrics_collector


def get_global_audit_logger() -> AuditLogger | None:
    """Get the global audit logger instance."""
    if _global_audit_logger is None:
        initialize_monitoring()
    return _global_audit_logger


def get_global_performance_monitor() -> PerformanceMonitor | None:
    """Get the global performance monitor instance."""
    if _global_performance_monitor is None:
        initialize_monitoring()
    return _global_performance_monitor
