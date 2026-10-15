"""
S3 Storage Client implementation utilizing boto3 and botocore.
Provides streaming uploads with SHA-256 integrity calculation, presigned URLs,
metadata inspection, and bucket health checking.
"""

import hashlib
import re
import tempfile
import uuid
from datetime import UTC, datetime
from typing import BinaryIO
from urllib.parse import urlparse, urlunparse

import boto3
from botocore.client import Config
from botocore.exceptions import (
    ClientError,
    ConnectTimeoutError,
    EndpointConnectionError,
    ReadTimeoutError,
)

from app.audit import log_storage_event
from app.config import Settings
from app.models import (
    DeleteFileResponse,
    DirectUploadResponse,
    FileMetadataResponse,
    PresignedDownloadResponse,
    PresignedUploadResponse,
)

SAFE_PATH_REGEX = re.compile(r"^[a-zA-Z0-9_\-\./]+$")


class StorageError(Exception):
    """Base exception for storage operations."""


class StorageNotFoundError(StorageError):
    """Raised when an object or bucket is not found."""


class StorageAuthenticationError(StorageError):
    """Raised on authentication or permission issues with S3."""


class StorageConnectionError(StorageError):
    """Raised on network timeouts or unreachable endpoints."""


class StorageValidationError(StorageError):
    """Raised on invalid input or security validation failures."""


def sanitize_file_id(file_id: str) -> str:
    """
    Validates and normalizes file_id to prevent directory traversal or malformed paths.
    """
    if not file_id:
        raise StorageValidationError("File ID darf nicht leer sein.")
    clean = file_id.strip()
    if clean.startswith("/") or clean.endswith("/"):
        raise StorageValidationError("File ID darf nicht mit '/' beginnen oder enden.")
    if not SAFE_PATH_REGEX.match(clean):
        raise StorageValidationError("File ID enthält unzulässige Zeichen.")
    parts = clean.split("/")
    for part in parts:
        if part in ("", ".", ".."):
            raise StorageValidationError(
                "Ungültiger Pfadbestandteil in File ID (Path Traversal abgewiesen)."
            )
    return "/".join(parts)


def replace_public_endpoint(url: str, public_endpoint: str | None) -> str:
    """
    Replaces internal hostname/scheme with a public endpoint URL if configured.
    """
    if not public_endpoint:
        return url
    parsed_url = urlparse(url)
    parsed_pub = urlparse(public_endpoint)
    new_url = parsed_url._replace(scheme=parsed_pub.scheme, netloc=parsed_pub.netloc)
    return urlunparse(new_url)


class S3StorageClient:
    """
    Enterprise S3-compatible client wrapper with automatic retries and timeouts.
    """

    def __init__(self, settings: Settings, boto3_client=None):
        self.settings = settings
        self.bucket = settings.storage_bucket
        self.public_endpoint = settings.storage_public_endpoint_url
        self._external_client = boto3_client

    def _get_client(self):
        if self._external_client is not None:
            return self._external_client

        botocore_config = Config(
            signature_version="s3v4",
            s3={"addressing_style": self.settings.storage_addressing_style},
            connect_timeout=self.settings.connect_timeout_seconds,
            read_timeout=self.settings.read_timeout_seconds,
            retries={
                "max_attempts": self.settings.max_retries,
                "mode": "standard",
            },
        )

        return boto3.client(
            "s3",
            endpoint_url=self.settings.storage_endpoint_url,
            aws_access_key_id=self.settings.storage_access_key,
            aws_secret_access_key=self.settings.storage_secret_key,
            region_name=self.settings.storage_region,
            config=botocore_config,
        )

    def upload_stream(
        self,
        stream: BinaryIO,
        filename: str,
        content_type: str,
        file_id: str | None = None,
        custom_metadata: dict[str, str] | None = None,
    ) -> DirectUploadResponse:
        """
        Streams binary data to S3 while computing SHA-256 and enforcing max size.
        """
        clean_filename = filename.strip().replace("\\", "/").split("/")[-1]
        if not clean_filename:
            clean_filename = "document.bin"

        if file_id:
            storage_path = sanitize_file_id(file_id)
        else:
            unique_prefix = uuid.uuid4().hex[:16]
            storage_path = f"uploads/{unique_prefix}/{clean_filename}"

        hasher = hashlib.sha256()
        total_bytes = 0
        chunk_size = 65536  # 64 KB chunks

        # Use SpooledTemporaryFile to buffer stream efficiently without excessive RAM use
        with tempfile.SpooledTemporaryFile(max_size=10 * 1024 * 1024) as temp_buffer:
            while True:
                chunk = stream.read(chunk_size)
                if not chunk:
                    break
                total_bytes += len(chunk)
                if total_bytes > self.settings.max_upload_size_bytes:
                    raise StorageValidationError(
                        f"Dateigröße ({total_bytes} Bytes) überschreitet das Limit von {self.settings.max_upload_size_bytes} Bytes."
                    )
                hasher.update(chunk)
                temp_buffer.write(chunk)

            sha256_hex = hasher.hexdigest()
            temp_buffer.seek(0)

            metadata = {
                "sha256": sha256_hex,
                "original-filename": clean_filename,
            }
            if custom_metadata:
                for k, v in custom_metadata.items():
                    safe_k = k.lower().replace("_", "-")
                    metadata[safe_k] = str(v)

            s3 = self._get_client()
            try:
                put_result = s3.put_object(
                    Bucket=self.bucket,
                    Key=storage_path,
                    Body=temp_buffer,
                    ContentType=content_type,
                    Metadata=metadata,
                )
                etag = put_result.get("ETag", "").strip('"')
            except (
                EndpointConnectionError,
                ConnectTimeoutError,
                ReadTimeoutError,
            ) as e:
                log_storage_event(
                    "s3.upload_connection_error", str(e), data={"path": storage_path}
                )
                raise StorageConnectionError(
                    f"Verbindungsfehler zum S3-Speicher: {e}"
                ) from e
            except ClientError as e:
                error_code = e.response.get("Error", {}).get("Code", "")
                log_storage_event(
                    "s3.upload_client_error",
                    str(e),
                    data={"code": error_code, "path": storage_path},
                )
                if error_code in (
                    "InvalidAccessKeyId",
                    "SignatureDoesNotMatch",
                    "AccessDenied",
                ):
                    raise StorageAuthenticationError(
                        f"Authentifizierungsfehler bei S3: {error_code}"
                    ) from e
                raise StorageError(f"S3-Fehler beim Upload ({error_code}): {e}") from e

        log_storage_event(
            "s3.upload_completed",
            f"File uploaded successfully: {storage_path}",
            data={
                "storage_path": storage_path,
                "size_bytes": total_bytes,
                "sha256": sha256_hex,
                "content_type": content_type,
            },
        )

        return DirectUploadResponse(
            file_id=storage_path,
            filename=clean_filename,
            content_type=content_type,
            size_bytes=total_bytes,
            sha256_hash=sha256_hex,
            storage_path=storage_path,
            created_at=datetime.now(UTC),
            etag=etag,
        )

    def generate_presigned_upload(
        self,
        filename: str,
        content_type: str,
        file_id: str | None = None,
        ttl_seconds: int = 3600,
        sha256_hash: str | None = None,
        custom_metadata: dict[str, str] | None = None,
    ) -> PresignedUploadResponse:
        """
        Generates a cryptographically signed PUT URL for direct client upload.
        """
        clean_filename = filename.strip().replace("\\", "/").split("/")[-1]
        if not clean_filename:
            clean_filename = "upload.bin"

        if file_id:
            storage_path = sanitize_file_id(file_id)
        else:
            unique_prefix = uuid.uuid4().hex[:16]
            storage_path = f"presigned/{unique_prefix}/{clean_filename}"

        metadata = {"original-filename": clean_filename}
        if sha256_hash:
            metadata["sha256"] = sha256_hash
        if custom_metadata:
            for k, v in custom_metadata.items():
                metadata[k.lower().replace("_", "-")] = str(v)

        params = {
            "Bucket": self.bucket,
            "Key": storage_path,
            "ContentType": content_type,
            "Metadata": metadata,
        }

        s3 = self._get_client()
        try:
            url = s3.generate_presigned_url(
                ClientMethod="put_object",
                Params=params,
                ExpiresIn=ttl_seconds,
                HttpMethod="PUT",
            )
        except Exception as e:
            log_storage_event(
                "s3.presigned_upload_error", str(e), data={"path": storage_path}
            )
            raise StorageError(
                f"Fehler bei Erzeugung der Pre-Signed Upload-URL: {e}"
            ) from e

        final_url = replace_public_endpoint(url, self.public_endpoint)

        required_headers = {"Content-Type": content_type}
        for k, v in metadata.items():
            required_headers[f"x-amz-meta-{k}"] = v

        log_storage_event(
            "s3.presigned_upload_created",
            f"Presigned upload URL created for {storage_path}",
            data={"storage_path": storage_path, "ttl": ttl_seconds},
        )

        return PresignedUploadResponse(
            file_id=storage_path,
            upload_url=final_url,
            method="PUT",
            headers=required_headers,
            expires_in_seconds=ttl_seconds,
            storage_path=storage_path,
        )

    def generate_presigned_download(
        self,
        file_id: str,
        ttl_seconds: int = 3600,
        download_filename: str | None = None,
    ) -> PresignedDownloadResponse:
        """
        Generates a cryptographically signed GET URL for direct file download.
        """
        storage_path = sanitize_file_id(file_id)
        params = {"Bucket": self.bucket, "Key": storage_path}

        if download_filename:
            clean_name = (
                download_filename.strip()
                .replace('"', "")
                .replace("\\", "/")
                .split("/")[-1]
            )
            if clean_name:
                params["ResponseContentDisposition"] = (
                    f'attachment; filename="{clean_name}"'
                )

        s3 = self._get_client()
        try:
            url = s3.generate_presigned_url(
                ClientMethod="get_object",
                Params=params,
                ExpiresIn=ttl_seconds,
            )
        except Exception as e:
            log_storage_event(
                "s3.presigned_download_error", str(e), data={"path": storage_path}
            )
            raise StorageError(
                f"Fehler bei Erzeugung der Pre-Signed Download-URL: {e}"
            ) from e

        final_url = replace_public_endpoint(url, self.public_endpoint)

        log_storage_event(
            "s3.presigned_download_created",
            f"Presigned download URL created for {storage_path}",
            data={"storage_path": storage_path, "ttl": ttl_seconds},
        )

        return PresignedDownloadResponse(
            file_id=storage_path,
            download_url=final_url,
            expires_in_seconds=ttl_seconds,
        )

    def get_metadata(self, file_id: str) -> FileMetadataResponse:
        """
        Retrieves file metadata from S3 using HeadObject.
        """
        storage_path = sanitize_file_id(file_id)
        s3 = self._get_client()

        try:
            head = s3.head_object(Bucket=self.bucket, Key=storage_path)
        except (EndpointConnectionError, ConnectTimeoutError, ReadTimeoutError) as e:
            raise StorageConnectionError(
                f"Verbindungsfehler beim Abruf von Metadaten: {e}"
            ) from e
        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "")
            if error_code in ("404", "NoSuchKey"):
                raise StorageNotFoundError(
                    f"Datei '{file_id}' wurde nicht gefunden."
                ) from e
            if error_code in (
                "InvalidAccessKeyId",
                "SignatureDoesNotMatch",
                "AccessDenied",
            ):
                raise StorageAuthenticationError(
                    f"Authentifizierungsfehler bei S3: {error_code}"
                ) from e
            raise StorageError(
                f"S3 Fehler bei Metadatenabfrage ({error_code}): {e}"
            ) from e

        metadata_dict = head.get("Metadata", {})
        sha256_hash = (
            metadata_dict.get("sha256") or metadata_dict.get("x-amz-meta-sha256") or ""
        )
        original_filename = (
            metadata_dict.get("original-filename")
            or metadata_dict.get("original_filename")
            or storage_path.split("/")[-1]
        )
        etag = head.get("ETag", "").strip('"')

        return FileMetadataResponse(
            file_id=storage_path,
            filename=original_filename,
            content_type=head.get("ContentType", "application/octet-stream"),
            size_bytes=head.get("ContentLength", 0),
            sha256_hash=sha256_hash,
            etag=etag,
            last_modified=head.get("LastModified"),
            custom_metadata=metadata_dict,
        )

    def delete_file(self, file_id: str) -> DeleteFileResponse:
        """
        Verifies existence and securely deletes the object from S3.
        """
        storage_path = sanitize_file_id(file_id)
        s3 = self._get_client()

        # Check existence first
        try:
            s3.head_object(Bucket=self.bucket, Key=storage_path)
        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "")
            if error_code in ("404", "NoSuchKey"):
                raise StorageNotFoundError(
                    f"Datei '{file_id}' existiert nicht und kann nicht gelöscht werden."
                ) from e
            raise StorageError(
                f"Fehler bei Existenzprüfung vor dem Löschen: {e}"
            ) from e

        try:
            s3.delete_object(Bucket=self.bucket, Key=storage_path)
        except (EndpointConnectionError, ConnectTimeoutError, ReadTimeoutError) as e:
            raise StorageConnectionError(
                f"Verbindungsfehler beim Löschen der Datei: {e}"
            ) from e
        except ClientError as e:
            raise StorageError(f"Fehler beim Löschen des S3-Objekts: {e}") from e

        log_storage_event(
            "s3.file_deleted",
            f"File deleted successfully: {storage_path}",
            data={"storage_path": storage_path},
        )

        return DeleteFileResponse(
            file_id=storage_path,
            deleted=True,
            message="Datei erfolgreich aus dem Objektspeicher gelöscht.",
        )

    def check_bucket_ready(self) -> bool:
        """
        Checks if the S3 bucket exists and is accessible.
        """
        s3 = self._get_client()
        try:
            s3.head_bucket(Bucket=self.bucket)
            return True
        except Exception as e:  # noqa: BLE001
            log_storage_event(
                "s3.readiness_check_failed", str(e), data={"bucket": self.bucket}
            )
            return False
