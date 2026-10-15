"""Unit and contract tests for StorageClient (S3 Object Storage)."""

import io
import json

import httpx
import pytest

from vibecore.exceptions import (
    StorageAuthenticationError,
    StorageNotFoundError,
    StorageValidationError,
)
from vibecore.storage.client import StorageClient
from vibecore.storage.models import (
    DeleteFileResponse,
    DirectUploadResponse,
    FileMetadataResponse,
    HealthResponse,
    PresignedDownloadResponse,
    PresignedUploadResponse,
    ReadyResponse,
)


def test_storage_client_health():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/health"
        return httpx.Response(200, json={"status": "ok", "version": "0.1.0"})

    with StorageClient("http://storage.test", transport=httpx.MockTransport(handler)) as client:
        health = client.health()
        assert isinstance(health, HealthResponse)
        assert health.status == "ok"
        assert health.version == "0.1.0"


def test_storage_client_ready():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/ready"
        return httpx.Response(
            200,
            json={
                "status": "ready",
                "bucket": "vibecore-documents",
                "storage_connected": True,
                "endpoint": "http://minio:9000",
            },
        )

    with StorageClient("http://storage.test", transport=httpx.MockTransport(handler)) as client:
        ready = client.ready()
        assert isinstance(ready, ReadyResponse)
        assert ready.status == "ready"
        assert ready.storage_connected is True
        assert ready.bucket == "vibecore-documents"


def test_storage_client_upload_bytes():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v1/storage/upload"
        assert request.method == "POST"
        assert "multipart/form-data" in request.headers.get("content-type", "")
        assert request.headers.get("x-api-key") == "secret-storage-key"
        return httpx.Response(
            201,
            json={
                "file_id": "docs/invoice_1001.pdf",
                "filename": "invoice_1001.pdf",
                "content_type": "application/pdf",
                "size_bytes": 1024,
                "sha256_hash": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
                "storage_path": "docs/invoice_1001.pdf",
                "etag": '"etag-123"',
            },
        )

    client = StorageClient(
        "http://storage.test",
        api_key="secret-storage-key",
        transport=httpx.MockTransport(handler),
    )
    result = client.upload(
        file=b"%PDF-1.4 mock content",
        filename="invoice_1001.pdf",
        content_type="application/pdf",
        file_id="docs/invoice_1001.pdf",
        custom_metadata={"doc_type": "tax_invoice"},
    )
    assert isinstance(result, DirectUploadResponse)
    assert result.file_id == "docs/invoice_1001.pdf"
    assert result.size_bytes == 1024
    assert result.content_type == "application/pdf"
    client.close()


def test_storage_client_upload_stream():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v1/storage/upload"
        return httpx.Response(
            201,
            json={
                "file_id": "stream_test.txt",
                "filename": "stream_test.txt",
                "content_type": "text/plain",
                "size_bytes": 12,
                "sha256_hash": "a" * 64,
                "storage_path": "stream_test.txt",
            },
        )

    with StorageClient("http://storage.test", transport=httpx.MockTransport(handler)) as client:
        stream = io.BytesIO(b"Hello world!")
        result = client.upload(file=stream, filename="stream_test.txt", content_type="text/plain")
        assert result.file_id == "stream_test.txt"
        assert result.size_bytes == 12


def test_storage_client_get_presigned_upload_url():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v1/storage/presigned-upload"
        body = json.loads(request.content.decode("utf-8"))
        assert body["filename"] == "large_backup.tar.gz"
        assert body["content_type"] == "application/gzip"
        assert body["ttl_seconds"] == 7200
        return httpx.Response(
            200,
            json={
                "file_id": "large_backup.tar.gz",
                "upload_url": "https://s3.amazonaws.com/bucket/large_backup.tar.gz?AWSAccessKeyId=...",
                "method": "PUT",
                "headers": {"Content-Type": "application/gzip"},
                "expires_in_seconds": 7200,
                "storage_path": "large_backup.tar.gz",
            },
        )

    with StorageClient("http://storage.test", transport=httpx.MockTransport(handler)) as client:
        presigned = client.get_presigned_upload_url(
            filename="large_backup.tar.gz",
            content_type="application/gzip",
            ttl_seconds=7200,
        )
        assert isinstance(presigned, PresignedUploadResponse)
        assert presigned.method == "PUT"
        assert presigned.expires_in_seconds == 7200
        assert presigned.upload_url.startswith("https://s3.amazonaws.com")


def test_storage_client_get_presigned_download_url():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v1/storage/presigned-download"
        body = json.loads(request.content.decode("utf-8"))
        assert body["file_id"] == "docs/receipt.png"
        return httpx.Response(
            200,
            json={
                "file_id": "docs/receipt.png",
                "download_url": "https://s3.amazonaws.com/bucket/docs/receipt.png?AWSAccessKeyId=...",
                "expires_in_seconds": 3600,
            },
        )

    with StorageClient("http://storage.test", transport=httpx.MockTransport(handler)) as client:
        resp = client.get_presigned_download_url("docs/receipt.png")
        assert isinstance(resp, PresignedDownloadResponse)
        assert resp.file_id == "docs/receipt.png"
        assert resp.download_url.startswith("https://s3.amazonaws.com")


def test_storage_client_get_metadata():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v1/storage/files/docs/tax.xml/metadata"
        return httpx.Response(
            200,
            json={
                "file_id": "docs/tax.xml",
                "filename": "tax.xml",
                "content_type": "application/xml",
                "size_bytes": 4500,
                "sha256_hash": "b" * 64,
                "etag": '"etag-xml"',
                "custom_metadata": {"iva_rate": "10"},
            },
        )

    with StorageClient("http://storage.test", transport=httpx.MockTransport(handler)) as client:
        meta = client.get_metadata("docs/tax.xml")
        assert isinstance(meta, FileMetadataResponse)
        assert meta.size_bytes == 4500
        assert meta.content_type == "application/xml"
        assert meta.custom_metadata["iva_rate"] == "10"


def test_storage_client_not_found_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"detail": "Datei 'missing.pdf' nicht gefunden."})

    with StorageClient("http://storage.test", transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(StorageNotFoundError) as exc_info:
            client.get_metadata("missing.pdf")
        assert exc_info.value.status_code == 404
        assert "nicht gefunden" in str(exc_info.value)


def test_storage_client_validation_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"detail": "Ungültiger Dateiname: ungültige Zeichen"})

    with StorageClient("http://storage.test", transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(StorageValidationError) as exc_info:
            client.get_presigned_upload_url(filename="..", content_type="text/plain")
        assert exc_info.value.status_code == 400


def test_storage_client_auth_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"detail": "Ungültiger oder fehlender API-Key"})

    with StorageClient("http://storage.test", transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(StorageAuthenticationError) as exc_info:
            client.delete("some_file.pdf")
        assert exc_info.value.status_code == 401


def test_storage_client_delete():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v1/storage/files/old_doc.pdf"
        assert request.method == "DELETE"
        return httpx.Response(
            200,
            json={
                "file_id": "old_doc.pdf",
                "deleted": True,
                "message": "Datei erfolgreich gelöscht",
            },
        )

    with StorageClient("http://storage.test", transport=httpx.MockTransport(handler)) as client:
        resp = client.delete("old_doc.pdf")
        assert isinstance(resp, DeleteFileResponse)
        assert resp.deleted is True
        assert resp.file_id == "old_doc.pdf"
