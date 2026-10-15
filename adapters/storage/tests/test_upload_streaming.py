"""
Tests for direct streaming upload functionality, SHA-256 integrity, and size limits (Säule 2).
"""

import hashlib
import io
import json


def test_direct_upload_pdf_success(client, test_settings, raw_s3_client, sample_pdf):
    headers = {"X-API-Key": test_settings.storage_api_key}
    files = {
        "file": (
            sample_pdf["filename"],
            io.BytesIO(sample_pdf["content"]),
            sample_pdf["content_type"],
        )
    }

    response = client.post("/api/v1/storage/upload", headers=headers, files=files)
    assert response.status_code == 201
    data = response.json()

    assert data["filename"] == sample_pdf["filename"]
    assert data["content_type"] == sample_pdf["content_type"]
    assert data["size_bytes"] == len(sample_pdf["content"])

    expected_sha256 = hashlib.sha256(sample_pdf["content"]).hexdigest()
    assert data["sha256_hash"] == expected_sha256

    file_id = data["file_id"]
    head = raw_s3_client.head_object(Bucket=test_settings.storage_bucket, Key=file_id)
    assert head["ContentLength"] == len(sample_pdf["content"])
    assert head["Metadata"]["sha256"] == expected_sha256


def test_direct_upload_with_custom_file_id(
    client, test_settings, raw_s3_client, sample_pdf
):
    headers = {"X-API-Key": test_settings.storage_api_key}
    custom_id = "documents/invoices/2026/fac_001.pdf"
    files = {
        "file": (
            sample_pdf["filename"],
            io.BytesIO(sample_pdf["content"]),
            sample_pdf["content_type"],
        )
    }
    data = {"file_id": custom_id}

    response = client.post(
        "/api/v1/storage/upload", headers=headers, files=files, data=data
    )
    assert response.status_code == 201
    res_data = response.json()
    assert res_data["file_id"] == custom_id

    # Verify directly in S3
    head = raw_s3_client.head_object(Bucket=test_settings.storage_bucket, Key=custom_id)
    assert head["ContentLength"] == len(sample_pdf["content"])


def test_direct_upload_with_custom_metadata(
    client, test_settings, raw_s3_client, sample_xml
):
    headers = {"X-API-Key": test_settings.storage_api_key}
    meta_dict = {"sifen-cdc": "01800123456789", "fiscal-year": "2026"}
    files = {
        "file": (
            sample_xml["filename"],
            io.BytesIO(sample_xml["content"]),
            sample_xml["content_type"],
        )
    }
    data = {"custom_metadata": json.dumps(meta_dict)}

    response = client.post(
        "/api/v1/storage/upload", headers=headers, files=files, data=data
    )
    assert response.status_code == 201
    res_data = response.json()

    head = raw_s3_client.head_object(
        Bucket=test_settings.storage_bucket, Key=res_data["file_id"]
    )
    assert head["Metadata"]["sifen-cdc"] == "01800123456789"
    assert head["Metadata"]["fiscal-year"] == "2026"


def test_direct_upload_disallowed_content_type(client, test_settings):
    headers = {"X-API-Key": test_settings.storage_api_key}
    files = {
        "file": (
            "malware.exe",
            io.BytesIO(b"MZ\x90\x00executable"),
            "application/x-msdownload",
        )
    }

    response = client.post("/api/v1/storage/upload", headers=headers, files=files)
    assert response.status_code == 400
    assert "Content-Type" in response.json()["message"]


def test_direct_upload_exceeds_max_size(client, test_settings):
    headers = {"X-API-Key": test_settings.storage_api_key}
    # Limit is 10 MB in test_settings. Send 11 MB.
    oversized_data = b"X" * (11 * 1024 * 1024)
    files = {"file": ("huge_file.pdf", io.BytesIO(oversized_data), "application/pdf")}

    response = client.post("/api/v1/storage/upload", headers=headers, files=files)
    assert response.status_code == 400
    assert "überschreitet das Limit" in response.json()["message"]


def test_direct_upload_path_traversal_rejection(client, test_settings, sample_pdf):
    headers = {"X-API-Key": test_settings.storage_api_key}
    files = {
        "file": (
            sample_pdf["filename"],
            io.BytesIO(sample_pdf["content"]),
            sample_pdf["content_type"],
        )
    }
    data = {"file_id": "../../../etc/passwd"}

    response = client.post(
        "/api/v1/storage/upload", headers=headers, files=files, data=data
    )
    assert response.status_code == 400
    assert "Path Traversal" in response.json()["message"]


def test_direct_upload_invalid_custom_metadata_json(client, test_settings, sample_pdf):
    headers = {"X-API-Key": test_settings.storage_api_key}
    files = {
        "file": (
            sample_pdf["filename"],
            io.BytesIO(sample_pdf["content"]),
            sample_pdf["content_type"],
        )
    }
    data = {"custom_metadata": "not-a-json-string"}

    response = client.post(
        "/api/v1/storage/upload", headers=headers, files=files, data=data
    )
    assert response.status_code == 400
    assert "Ungültiges JSON-Format" in response.json()["message"]
