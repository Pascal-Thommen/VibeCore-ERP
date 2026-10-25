"""
Tests for Observability, Healthchecks, and Prometheus Metrics (Säule 4: Observability).
"""

from app.metrics import metrics_registry


def test_healthz_and_readyz_endpoints(client):
    res_healthz = client.get("/healthz")
    assert res_healthz.status_code == 200
    data_h = res_healthz.json()
    assert data_h["status"] == "healthy"
    assert "version" in data_h
    assert "meta" in data_h
    assert data_h["meta"]["algorithm"] == "RS256"

    # Alias /health
    res_health = client.get("/health")
    assert res_health.status_code == 200
    assert res_health.json()["status"] == "healthy"

    # Readiness
    res_readyz = client.get("/readyz")
    assert res_readyz.status_code == 200
    data_r = res_readyz.json()
    assert data_r["status"] == "ready"
    assert data_r["checks"]["asymmetric_crypto_keys"] is True

    # Alias /ready
    res_ready = client.get("/ready")
    assert res_ready.status_code == 200


def test_prometheus_metrics_endpoint(client):
    # Make a couple of requests to populate metrics
    client.get("/healthz")
    client.get("/readyz")

    res = client.get("/metrics")
    assert res.status_code == 200
    assert "text/plain" in res.headers["content-type"]
    text = res.text

    # Verify Prometheus exposition format
    assert "# HELP vibecore_auth_http_requests_total" in text
    assert "# TYPE vibecore_auth_http_requests_total counter" in text
    assert 'vibecore_auth_http_requests_total{endpoint="/healthz"' in text
    assert "# HELP vibecore_auth_tokens_issued_total" in text


def test_trace_id_propagation_and_correlation(client):
    custom_tid = "custom_test_trace_123456"
    res = client.get("/healthz", headers={"X-Trace-Id": custom_tid})
    assert res.status_code == 200
    assert res.headers["X-Trace-Id"] == custom_tid

    # When no trace ID provided, system generates one starting with vc_tr_
    res2 = client.get("/healthz")
    assert "X-Trace-Id" in res2.headers
    assert res2.headers["X-Trace-Id"].startswith("vc_tr_")


def test_metrics_registry_unit_methods():
    metrics_registry.inc_counter("test_counter", 2.0, {"env": "test"})
    metrics_registry.set_gauge("test_gauge", 42.0)
    metrics_registry.record_exception("TestError")

    text = metrics_registry.generate_prometheus_text()
    assert "test_counter" in text
    assert "test_gauge" in text
    assert "vibecore_auth_exceptions_total" in text
