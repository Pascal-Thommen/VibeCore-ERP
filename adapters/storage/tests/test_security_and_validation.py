"""
Tests for Säule 3 (Security & Access Control): API Keys, Input Sanitization, and Validation.
"""

import io

import pytest
from app.client import StorageValidationError, sanitize_file_id


def test_api_key_missing_rejected(client, sample_pdf):
    # No X-API-Key header provided
    files = {
        "file": (
            sample_pdf["filename"],
            io.BytesIO(sample_pdf["content"]),
            sample_pdf["content_type"],
        )
    }
    response = client.post("/api/v1/storage/upload", files=files)
    assert response.status_code == 401
    assert "fehlender API-Key" in response.json()["message"]


def test_api_key_invalid_rejected(client, sample_pdf):
    headers = {"X-API-Key": "completely-invalid-key"}
    files = {
        "file": (
            sample_pdf["filename"],
            io.BytesIO(sample_pdf["content"]),
            sample_pdf["content_type"],
        )
    }
    response = client.post("/api/v1/storage/upload", headers=headers, files=files)
    assert response.status_code == 401
    assert "Ungültiger oder fehlender API-Key" in response.json()["message"]


def test_sanitize_file_id_valid_cases():
    assert sanitize_file_id("docs/invoice_2026.pdf") == "docs/invoice_2026.pdf"
    assert sanitize_file_id("simple.png") == "simple.png"
    assert sanitize_file_id("folder-1/sub-2/file.txt") == "folder-1/sub-2/file.txt"


def test_sanitize_file_id_rejects_path_traversal():
    with pytest.raises(StorageValidationError):
        sanitize_file_id("../../../etc/passwd")

    with pytest.raises(StorageValidationError):
        sanitize_file_id("folder/../file.txt")

    with pytest.raises(StorageValidationError):
        sanitize_file_id("/absolute/path/file.pdf")

    with pytest.raises(StorageValidationError):
        sanitize_file_id("")


def test_sanitize_file_id_rejects_malicious_characters():
    with pytest.raises(StorageValidationError):
        sanitize_file_id("file;rm -rf /")

    with pytest.raises(StorageValidationError):
        sanitize_file_id("file\x00.pdf")

    with pytest.raises(StorageValidationError):
        sanitize_file_id("file$.pdf")


def test_validation_error_response_structure(client, test_settings):
    headers = {"X-API-Key": test_settings.storage_api_key}
    # Send invalid JSON schema for presigned upload (missing required fields)
    response = client.post(
        "/api/v1/storage/presigned-upload", headers=headers, json={"invalid": 123}
    )
    assert response.status_code == 422
    data = response.json()
    assert data["error"] == "validation_error"
    assert data["trace_id"] is not None


def test_presigned_upload_invalid_filename_in_model():
    from app.models import PresignedUploadRequest
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        PresignedUploadRequest(filename="..", content_type="application/pdf")

    with pytest.raises(ValidationError):
        PresignedUploadRequest(filename="/", content_type="application/pdf")


def test_generic_unhandled_exception_handler(test_settings):
    from unittest.mock import patch

    from app.main import app
    from fastapi.testclient import TestClient

    headers = {"X-API-Key": test_settings.storage_api_key}

    with (
        patch(
            "app.routers.storage.StorageService.get_metadata",
            side_effect=RuntimeError("Fatal database/storage failure"),
        ),
        TestClient(app, raise_server_exceptions=False) as err_client,
    ):
        response = err_client.get(
            "/api/v1/storage/files/test.pdf/metadata", headers=headers
        )
        assert response.status_code == 500
        data = response.json()
        assert data["error"] == "internal_error"
