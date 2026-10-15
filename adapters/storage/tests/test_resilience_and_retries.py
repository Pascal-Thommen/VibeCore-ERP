"""
Tests for Säule 1 (Resilience): Network timeouts, S3 disconnections, and retries.
"""

import io
from unittest.mock import MagicMock

from app.client import (
    S3StorageClient,
    StorageAuthenticationError,
    StorageConnectionError,
)
from app.routers.storage import get_storage_service
from app.service import StorageService
from botocore.exceptions import (
    ClientError,
    ConnectTimeoutError,
    EndpointConnectionError,
)


def test_network_connection_timeout_handling(client, test_settings):
    headers = {"X-API-Key": test_settings.storage_api_key}

    # Mock client that raises ConnectTimeoutError
    mock_boto = MagicMock()
    mock_boto.put_object.side_effect = ConnectTimeoutError(
        endpoint_url="https://s3.amazonaws.com"
    )

    err_storage_client = S3StorageClient(test_settings, boto3_client=mock_boto)
    err_service = StorageService(test_settings, client=err_storage_client)

    from app.main import app

    app.dependency_overrides[get_storage_service] = lambda: err_service

    try:
        files = {"file": ("test.pdf", io.BytesIO(b"%PDF-test"), "application/pdf")}
        response = client.post("/api/v1/storage/upload", headers=headers, files=files)
        assert response.status_code == 503
        data = response.json()
        assert data["error"] == "http_error"
        assert "Verbindungsfehler" in data["message"]
    finally:
        app.dependency_overrides.clear()


def test_endpoint_connection_error_on_metadata(client, test_settings):
    headers = {"X-API-Key": test_settings.storage_api_key}

    mock_boto = MagicMock()
    mock_boto.head_object.side_effect = EndpointConnectionError(
        endpoint_url="https://s3.amazonaws.com"
    )

    err_storage_client = S3StorageClient(test_settings, boto3_client=mock_boto)
    err_service = StorageService(test_settings, client=err_storage_client)

    from app.main import app

    app.dependency_overrides[get_storage_service] = lambda: err_service

    try:
        response = client.get("/api/v1/storage/files/any.pdf/metadata", headers=headers)
        assert response.status_code == 503
        assert "Verbindungsfehler" in response.json()["message"]
    finally:
        app.dependency_overrides.clear()


def test_s3_access_denied_mapped_to_forbidden(client, test_settings):
    headers = {"X-API-Key": test_settings.storage_api_key}

    mock_boto = MagicMock()
    mock_boto.put_object.side_effect = ClientError(
        {"Error": {"Code": "AccessDenied", "Message": "Access Denied"}},
        operation_name="PutObject",
    )

    err_storage_client = S3StorageClient(test_settings, boto3_client=mock_boto)
    err_service = StorageService(test_settings, client=err_storage_client)

    from app.main import app

    app.dependency_overrides[get_storage_service] = lambda: err_service

    try:
        files = {"file": ("test.pdf", io.BytesIO(b"%PDF-test"), "application/pdf")}
        response = client.post("/api/v1/storage/upload", headers=headers, files=files)
        assert response.status_code == 403
        assert "Authentifizierungsfehler" in response.json()["message"]
    finally:
        app.dependency_overrides.clear()


def test_storage_client_config_retry_parameters(test_settings):
    storage_client = S3StorageClient(test_settings)
    boto_client = storage_client._get_client()

    # Verify botocore client has retries and timeouts configured
    client_config = boto_client._client_config
    assert client_config.connect_timeout == test_settings.connect_timeout_seconds
    assert client_config.read_timeout == test_settings.read_timeout_seconds
    assert client_config.retries["mode"] == "standard"
    assert (
        client_config.retries.get("total_max_attempts") == test_settings.max_retries + 1
        or client_config.retries.get("max_attempts") == test_settings.max_retries
    )


def test_presigned_upload_connection_error(client, test_settings):
    from unittest.mock import patch

    headers = {"X-API-Key": test_settings.storage_api_key}

    with patch(
        "app.routers.storage.StorageService.generate_presigned_upload",
        side_effect=StorageConnectionError("Netzwerk unterbrochen"),
    ):
        payload = {"filename": "test.pdf", "content_type": "application/pdf"}
        res = client.post(
            "/api/v1/storage/presigned-upload", headers=headers, json=payload
        )
        assert res.status_code == 503
        assert "Netzwerk unterbrochen" in res.json()["message"]


def test_presigned_upload_auth_error(client, test_settings):
    from unittest.mock import patch

    headers = {"X-API-Key": test_settings.storage_api_key}

    with patch(
        "app.routers.storage.StorageService.generate_presigned_upload",
        side_effect=StorageAuthenticationError("Keine S3 Rechte"),
    ):
        payload = {"filename": "test.pdf", "content_type": "application/pdf"}
        res = client.post(
            "/api/v1/storage/presigned-upload", headers=headers, json=payload
        )
        assert res.status_code == 403
        assert "Keine S3 Rechte" in res.json()["message"]


def test_presigned_download_connection_error(client, test_settings):
    from unittest.mock import patch

    headers = {"X-API-Key": test_settings.storage_api_key}

    with patch(
        "app.routers.storage.StorageService.generate_presigned_download",
        side_effect=StorageConnectionError("Download Timeout"),
    ):
        payload = {"file_id": "test.pdf"}
        res = client.post(
            "/api/v1/storage/presigned-download", headers=headers, json=payload
        )
        assert res.status_code == 503
        assert "Download Timeout" in res.json()["message"]


def test_delete_file_connection_error(client, test_settings):
    from unittest.mock import patch

    headers = {"X-API-Key": test_settings.storage_api_key}

    with patch(
        "app.routers.storage.StorageService.delete_file",
        side_effect=StorageConnectionError("S3 unreachable on delete"),
    ):
        res = client.delete("/api/v1/storage/files/doc.pdf", headers=headers)
        assert res.status_code == 503
        assert "S3 unreachable on delete" in res.json()["message"]
