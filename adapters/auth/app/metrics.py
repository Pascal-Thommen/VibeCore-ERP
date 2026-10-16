"""
VibeCore ERP Auth Adapter - Prometheus Metrics Collector (Säule 4: Observability).
Lightweight, thread-safe Prometheus metrics registry exporting standard exposition format.
"""

from collections import defaultdict
import threading
import time
from typing import Any


class PrometheusMetricsRegistry:
    """
    In-memory Prometheus metrics collector supporting counters and gauges without external dependencies.
    """

    def __init__(self):
        self._lock = threading.Lock()
        # Key: (metric_name, tuple(sorted(labels.items()))) -> float
        self._counters: dict[tuple[str, tuple[tuple[str, str], ...]], float] = defaultdict(float)
        self._gauges: dict[tuple[str, tuple[tuple[str, str], ...]], float] = defaultdict(float)
        self._descriptions: dict[str, str] = {
            "vibecore_auth_http_requests_total": "Total number of HTTP requests processed by auth adapter",
            "vibecore_auth_tokens_issued_total": "Total count of issued JWT tokens categorized by type",
            "vibecore_auth_tokens_refreshed_total": "Total count of successful token refresh operations",
            "vibecore_auth_google_requests_total": "Total number of outbound Google OAuth API requests",
            "vibecore_auth_google_request_duration_seconds": "Duration in seconds for Google API calls",
            "vibecore_auth_active_tenants_total": "Unique tenant count observed by the service",
            "vibecore_auth_exceptions_total": "Total count of caught exceptions and authentication errors",
        }
        self._metric_types: dict[str, str] = {
            "vibecore_auth_http_requests_total": "counter",
            "vibecore_auth_tokens_issued_total": "counter",
            "vibecore_auth_tokens_refreshed_total": "counter",
            "vibecore_auth_google_requests_total": "counter",
            "vibecore_auth_google_request_duration_seconds": "gauge",
            "vibecore_auth_active_tenants_total": "gauge",
            "vibecore_auth_exceptions_total": "counter",
        }
        self._tenants_seen: set[str] = set()

    def inc_counter(self, name: str, value: float = 1.0, labels: dict[str, str] | None = None) -> None:
        """Increments a counter metric with optional labels."""
        label_tuple = tuple(sorted((labels or {}).items()))
        with self._lock:
            self._counters[(name, label_tuple)] += value

    def set_gauge(self, name: str, value: float, labels: dict[str, str] | None = None) -> None:
        """Sets a gauge metric value."""
        label_tuple = tuple(sorted((labels or {}).items()))
        with self._lock:
            self._gauges[(name, label_tuple)] = value

    def observe_tenant(self, tenant_id: str) -> None:
        """Records an active tenant identifier and updates the active tenants gauge."""
        with self._lock:
            self._tenants_seen.add(tenant_id)
            self._gauges[("vibecore_auth_active_tenants_total", ())] = float(len(self._tenants_seen))

    def record_http_request(self, method: str, endpoint: str, status_code: int) -> None:
        """Helper to record incoming HTTP request metrics."""
        self.inc_counter(
            "vibecore_auth_http_requests_total",
            1.0,
            {"method": method.upper(), "endpoint": endpoint, "status": str(status_code)},
        )

    def record_token_issued(self, token_type: str = "access") -> None:
        """Helper to record token issuance."""
        self.inc_counter(
            "vibecore_auth_tokens_issued_total",
            1.0,
            {"type": token_type},
        )

    def record_token_refreshed(self) -> None:
        """Helper to record token refresh."""
        self.inc_counter("vibecore_auth_tokens_refreshed_total", 1.0)

    def record_google_request(self, endpoint: str, status_code: int, duration_seconds: float) -> None:
        """Helper to record external Google API call metrics."""
        self.inc_counter(
            "vibecore_auth_google_requests_total",
            1.0,
            {"endpoint": endpoint, "status": str(status_code)},
        )
        self.set_gauge(
            "vibecore_auth_google_request_duration_seconds",
            round(duration_seconds, 4),
            {"endpoint": endpoint},
        )

    def record_exception(self, error_type: str) -> None:
        """Helper to record exceptions."""
        self.inc_counter("vibecore_auth_exceptions_total", 1.0, {"error_type": error_type})

    def generate_prometheus_text(self) -> str:
        """
        Generates standard Prometheus plain-text exposition representation.
        """
        lines: list[str] = []
        with self._lock:
            # Group counters by name
            all_metrics: dict[str, list[tuple[tuple[tuple[str, str], ...], float]]] = defaultdict(list)
            for (name, label_tuple), val in self._counters.items():
                all_metrics[name].append((label_tuple, val))
            for (name, label_tuple), val in self._gauges.items():
                all_metrics[name].append((label_tuple, val))

            for name in sorted(all_metrics.keys()):
                desc = self._descriptions.get(name, f"Metric {name}")
                m_type = self._metric_types.get(name, "untyped")
                lines.append(f"# HELP {name} {desc}")
                lines.append(f"# TYPE {name} {m_type}")

                for label_tuple, val in sorted(all_metrics[name]):
                    if label_tuple:
                        labels_str = ",".join(f'{k}="{v}"' for k, v in label_tuple)
                        lines.append(f"{name}{{{labels_str}}} {val}")
                    else:
                        lines.append(f"{name} {val}")

        return "\n".join(lines) + "\n"


metrics_registry = PrometheusMetricsRegistry()
