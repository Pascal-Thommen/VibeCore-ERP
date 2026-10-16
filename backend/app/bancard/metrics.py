"""Prometheus metrics collector and exporter for Bancard adapter."""

from __future__ import annotations

import threading
import time
from typing import Dict, Tuple


class MetricsRegistry:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        # (status, method) -> count
        self._transactions_total: Dict[Tuple[str, str], int] = {}
        # method -> (count, sum_seconds)
        self._latencies: Dict[str, Tuple[int, float]] = {}
        # status -> count
        self._webhook_dispatches_total: Dict[str, int] = {}
        self._dead_letter_total: int = 0

    def record_transaction(self, status: str, method: str, duration_seconds: float = 0.0) -> None:
        with self._lock:
            key = (status, method)
            self._transactions_total[key] = self._transactions_total.get(key, 0) + 1

            cnt, tot = self._latencies.get(method, (0, 0.0))
            self._latencies[method] = (cnt + 1, tot + duration_seconds)

    def record_webhook_dispatch(self, status: str) -> None:
        with self._lock:
            self._webhook_dispatches_total[status] = self._webhook_dispatches_total.get(status, 0) + 1

    def set_dead_letter_count(self, count: int) -> None:
        with self._lock:
            self._dead_letter_total = count

    def generate_prometheus_text(self) -> str:
        with self._lock:
            lines = [
                "# HELP bancard_transactions_total Total number of Bancard transactions by status and payment method.",
                "# TYPE bancard_transactions_total counter",
            ]
            for (status, method), count in sorted(self._transactions_total.items()):
                lines.append(f'bancard_transactions_total{{status="{status}",method="{method}"}} {count}')

            lines.extend([
                "# HELP bancard_payment_latency_seconds Payment operation latency summary in seconds.",
                "# TYPE bancard_payment_latency_seconds summary",
            ])
            for method, (cnt, tot) in sorted(self._latencies.items()):
                lines.append(f'bancard_payment_latency_seconds_count{{method="{method}"}} {cnt}')
                lines.append(f'bancard_payment_latency_seconds_sum{{method="{method}"}} {tot:.6f}')

            lines.extend([
                "# HELP bancard_webhook_dispatches_total Total outbound webhook notifications by delivery status.",
                "# TYPE bancard_webhook_dispatches_total counter",
            ])
            for status, count in sorted(self._webhook_dispatches_total.items()):
                lines.append(f'bancard_webhook_dispatches_total{{status="{status}"}} {count}')

            lines.extend([
                "# HELP bancard_dead_letter_total Number of un-deliverable dead-letter webhooks currently queued.",
                "# TYPE bancard_dead_letter_total gauge",
                f"bancard_dead_letter_total {self._dead_letter_total}",
            ])

            return "\n".join(lines) + "\n"


metrics = MetricsRegistry()
