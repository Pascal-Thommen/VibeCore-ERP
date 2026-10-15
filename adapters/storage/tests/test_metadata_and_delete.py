"""
Tests for file metadata inspection and secure deletion.
"""

import hashlib
import io

import pytest
from botocore.exceptions import ClientError


def test_get_metadata_success(client, test_settings, sample_xml):
    headers = {"X-API-Key": test_settings.storage_api_key}

    # Upload file first
    files = {
        "file": (
            sample_xml["filename"],
            io.BytesIO(sample_xml["content"]),
            sample_xml["content_type"],
        )
    }
    upload_res = client.post("/api/v1/storage/upload", headers=headers, files=files)
    assert upload_res.status_code == 201
    file_id = upload_res.json()["file_id"]

    # Query metadata
    meta_res = client.get(f"/api/v1/storage/files/{file_id}/metadata", headers=headers)
    assert meta_res.status_code == 200
    data = meta_res.json()

    assert data["file_id"] == file_id
    assert data["filename"] == sample_xml["filename"]
    assert data["content_type"] == sample_xml["content_type"]
    assert data["size_bytes"] == len(sample_xml["content"])
    assert data["sha256_hash"] == hashlib.sha256(sample_xml["content"]).hexdigest()
    assert data["etag"] is not None


def test_get_metadata_not_found(client, test_settings):
    headers = {"X-API-Key": test_settings.storage_api_key}
    meta_res = client.get(
        "/api/v1/storage/files/nonexistent/file.pdf/metadata", headers=headers
    )
    assert meta_res.status_code == 404
    assert "nicht gefunden" in meta_res.json()["message"]


def test_delete_file_success(client, test_settings, raw_s3_client, sample_pdf):
    headers = {"X-API-Key": test_settings.storage_api_key}

    # Upload file first
    files = {
        "file": (
            sample_pdf["filename"],
            io.BytesIO(sample_pdf["content"]),
            sample_pdf["content_type"],
        )
    }
    upload_res = client.post("/api/v1/storage/upload", headers=headers, files=files)
    assert upload_res.status_code == 201
    file_id = upload_res.json()["file_id"]

    # Delete file
    del_res = client.delete(f"/api/v1/storage/files/{file_id}", headers=headers)
    assert del_res.status_code == 200
    del_data = del_res.json()
    assert del_data["deleted"] is True

    # Verify gone from S3
    with pytest.raises(ClientError):
        raw_s3_client.head_object(Bucket=test_settings.storage_bucket, Key=file_id)


def test_delete_file_not_found(client, test_settings):
    headers = {"X-API-Key": test_settings.storage_api_key}
    del_res = client.delete("/api/v1/storage/files/missing/doc.pdf", headers=headers)
    assert del_res.status_code == 404
    assert "existiert nicht" in del_res.json()["message"]


def test_path_traversal_protection(client, test_settings):
    headers = {"X-API-Key": test_settings.storage_api_key}

    # Metadata request with ..
    res1 = client.get("/api/v1/storage/files/../secret.pdf/metadata", headers=headers)
    assert res1.status_code in (400, 404)

    # Delete request with ..
    res2 = client.delete("/api/v1/storage/files/dir/../../etc/passwd", headers=headers)
    assert res2.status_code in (400, 404)
