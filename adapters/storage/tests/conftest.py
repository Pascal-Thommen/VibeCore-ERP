"""
Pytest configuration and authentic S3 fixtures using moto for Zero-Mock compliance.
"""

import boto3
import pytest
from app.client import S3StorageClient
from app.config import Settings, get_settings
from app.main import app
from app.routers.health import get_storage_service as get_health_storage_service
from app.routers.storage import get_storage_service
from fastapi.testclient import TestClient
from moto import mock_aws


@pytest.fixture
def mock_s3_env():
    """Provides a clean in-memory S3 environment for tests."""
    with mock_aws():
        yield


@pytest.fixture
def test_settings():
    """Provides isolated test settings."""
    return Settings(
        storage_bucket="test-vibecore-documents",
        storage_region="us-east-1",
        storage_access_key="test-access-key",
        storage_secret_key="test-secret-key",
        storage_endpoint_url=None,
        storage_public_endpoint_url="https://storage.vibecore.org",
        storage_addressing_style="auto",
        storage_api_key="sec-test-api-key-123456",
        default_presigned_ttl_seconds=3600,
        max_upload_size_bytes=10 * 1024 * 1024,  # 10 MB limit for test
        connect_timeout_seconds=2.0,
        read_timeout_seconds=5.0,
        max_retries=2,
    )


@pytest.fixture
def raw_s3_client(mock_s3_env, test_settings):
    """Initializes real S3 client and creates the test bucket."""
    client = boto3.client(
        "s3",
        region_name=test_settings.storage_region,
        aws_access_key_id=test_settings.storage_access_key,
        aws_secret_access_key=test_settings.storage_secret_key,
    )
    client.create_bucket(Bucket=test_settings.storage_bucket)
    return client


@pytest.fixture
def storage_client(test_settings, raw_s3_client):
    """Returns an initialized S3StorageClient bound to the mock S3 bucket."""
    return S3StorageClient(settings=test_settings, boto3_client=raw_s3_client)


@pytest.fixture
def client(test_settings, storage_client):
    """
    FastAPI TestClient with overridden settings and storage service.
    """
    from app.service import StorageService

    service = StorageService(settings=test_settings, client=storage_client)

    app.dependency_overrides[get_settings] = lambda: test_settings
    app.dependency_overrides[get_storage_service] = lambda: service
    app.dependency_overrides[get_health_storage_service] = lambda: service

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()


@pytest.fixture
def sample_pdf():
    return {
        "filename": "factura_electronica_001.pdf",
        "content_type": "application/pdf",
        "content": b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\nxref\n0 4\ntrailer<</Size 4/Root 1 0 R>>\nstartxref\n149\n%%EOF\n",
    }


@pytest.fixture
def sample_xml():
    return {
        "filename": "de_sifen_12345.xml",
        "content_type": "application/xml",
        "content": b'<?xml version="1.0" encoding="UTF-8"?><rDE xmlns="http://ekuatia.set.gov.py/sifen/xsd"><dVerFor>150</dVerFor></rDE>',
    }
