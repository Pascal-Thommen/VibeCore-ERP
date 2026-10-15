"""
Tests for presigned upload and download URL generation and validation.
"""

import requests


def test_generate_presigned_upload_success(client, test_settings):
    headers = {"X-API-Key": test_settings.storage_api_key}
    payload = {
        "filename": "annual_report_2026.pdf",
        "content_type": "application/pdf",
        "ttl_seconds": 1800,
        "custom_metadata": {"department": "finance", "author": "pascal"},
    }

    response = client.post(
        "/api/v1/storage/presigned-upload", headers=headers, json=payload
    )
    assert response.status_code == 200
    data = response.json()

    assert data["method"] == "PUT"
    assert data["expires_in_seconds"] == 1800
    assert data["upload_url"].startswith(test_settings.storage_public_endpoint_url)
    assert data["headers"]["Content-Type"] == "application/pdf"
    assert data["headers"]["x-amz-meta-department"] == "finance"
    assert data["headers"]["x-amz-meta-author"] == "pascal"
    assert "annual_report_2026.pdf" in data["file_id"]


def test_presigned_upload_and_download_flow(
    client, test_settings, raw_s3_client, storage_client, sample_pdf
):
    # Temporarily remove public_endpoint so moto in-process URL can be tested with boto3/moto
    storage_client.public_endpoint = None

    headers = {"X-API-Key": test_settings.storage_api_key}
    upload_payload = {
        "filename": sample_pdf["filename"],
        "content_type": sample_pdf["content_type"],
        "ttl_seconds": 3600,
    }

    res_upload = client.post(
        "/api/v1/storage/presigned-upload", headers=headers, json=upload_payload
    )
    assert res_upload.status_code == 200
    upload_data = res_upload.json()
    file_id = upload_data["file_id"]
    put_url = upload_data["upload_url"]

    # Execute direct PUT against the presigned URL
    put_res = requests.put(
        put_url,
        data=sample_pdf["content"],
        headers={"Content-Type": sample_pdf["content_type"]},
    )
    assert put_res.status_code == 200

    # Verify object in S3
    head = raw_s3_client.head_object(Bucket=test_settings.storage_bucket, Key=file_id)
    assert head["ContentLength"] == len(sample_pdf["content"])

    # Generate presigned download URL
    download_payload = {
        "file_id": file_id,
        "ttl_seconds": 1800,
        "download_filename": "rechnung_kunde.pdf",
    }
    res_download = client.post(
        "/api/v1/storage/presigned-download", headers=headers, json=download_payload
    )
    assert res_download.status_code == 200
    download_data = res_download.json()
    get_url = download_data["download_url"]

    assert "response-content-disposition=" in get_url
    assert "rechnung_kunde.pdf" in get_url

    # Execute direct GET using the presigned download URL
    get_res = requests.get(get_url)
    assert get_res.status_code == 200
    assert get_res.content == sample_pdf["content"]


def test_presigned_url_ttl_boundaries(client, test_settings):
    headers = {"X-API-Key": test_settings.storage_api_key}

    # TTL below 60s
    res_low = client.post(
        "/api/v1/storage/presigned-upload",
        headers=headers,
        json={
            "filename": "test.pdf",
            "content_type": "application/pdf",
            "ttl_seconds": 30,
        },
    )
    assert res_low.status_code in (400, 422)

    # TTL above 86400s
    res_high = client.post(
        "/api/v1/storage/presigned-upload",
        headers=headers,
        json={
            "filename": "test.pdf",
            "content_type": "application/pdf",
            "ttl_seconds": 100000,
        },
    )
    assert res_high.status_code in (400, 422)


def test_presigned_upload_disallowed_content_type(client, test_settings):
    headers = {"X-API-Key": test_settings.storage_api_key}
    res = client.post(
        "/api/v1/storage/presigned-upload",
        headers=headers,
        json={"filename": "script.sh", "content_type": "application/x-sh"},
    )
    assert res.status_code == 400
    assert "nicht autorisiert" in res.json()["message"]


def test_presigned_download_nonexistent_file(client, test_settings):
    headers = {"X-API-Key": test_settings.storage_api_key}
    # Download URL generation works based on signed token; let's check path traversal
    res = client.post(
        "/api/v1/storage/presigned-download",
        headers=headers,
        json={"file_id": "../../../secret"},
    )
    assert res.status_code == 400
    assert "Path Traversal" in res.json()["message"]
