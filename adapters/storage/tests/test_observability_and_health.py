"""
Tests for Säule 4 (Observability): Healthchecks, Correlation IDs, and Structured Logging.
"""

from unittest.mock import MagicMock

from app.audit import sanitize_dict
from app.client import S3StorageClient
from app.routers.health import get_storage_service as get_health_storage_service
from app.service import StorageService


def test_health_liveness_probe(client):
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["version"] == "0.1.0"
    assert "timestamp" in data


def test_ready_probe_success(client, test_settings):
    response = client.get("/ready")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ready"
    assert data["storage_connected"] is True
    assert data["bucket"] == test_settings.storage_bucket


def test_ready_probe_failure_returns_503(client, test_settings):
    # Mock client where check_bucket_ready fails
    mock_boto = MagicMock()
    mock_boto.head_bucket.side_effect = Exception("Bucket not accessible")

    unready_storage_client = S3StorageClient(test_settings, boto3_client=mock_boto)
    unready_service = StorageService(test_settings, client=unready_storage_client)

    from app.main import app

    app.dependency_overrides[get_health_storage_service] = lambda: unready_service

    try:
        response = client.get("/ready")
        assert response.status_code == 503
        data = response.json()
        assert data["status"] == "unready"
        assert data["storage_connected"] is False
    finally:
        app.dependency_overrides.clear()


def test_correlation_id_propagation(client):
    custom_cid = "custom-test-trace-id-98765"
    response = client.get("/health", headers={"X-Correlation-ID": custom_cid})
    assert response.status_code == 200
    assert response.headers["X-Correlation-ID"] == custom_cid


def test_correlation_id_auto_generated(client):
    response = client.get("/health")
    assert response.status_code == 200
    cid = response.headers.get("X-Correlation-ID")
    assert cid is not None
    assert cid.startswith("vc_stor_")


def test_audit_log_sanitization():
    raw_data = {
        "user": "pascal",
        "storage_secret_key": "very-secret-aws-key-do-not-leak",
        "api_key": "secret-api-key",
        "bucket": "vibecore-documents",
        "nested": {
            "password": "supersecretpassword",
            "normal_field": "visible",
        },
    }

    sanitized = sanitize_dict(raw_data)
    assert sanitized["user"] == "pascal"
    assert sanitized["bucket"] == "vibecore-documents"
    assert "REDACTED" in sanitized["storage_secret_key"]
    assert "very-secret-aws-key-do-not-leak" not in sanitized["storage_secret_key"]
    assert "REDACTED" in sanitized["api_key"]
    assert "REDACTED" in sanitized["nested"]["password"]
    assert sanitized["nested"]["normal_field"] == "visible"
