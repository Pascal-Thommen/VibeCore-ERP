"""Cryptographically secure OTP generation, salted SHA-256 hashing, and verification logic."""

from __future__ import annotations

import hashlib
import re
import secrets
import threading
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from app.config import settings
from app.schemas import OtpStatus, OtpVerifyResponse


def normalize_phone_number(raw_phone: str) -> str:
    """Normalize phone numbers to digits only, stripping +, whitespace, and dashes."""
    digits = re.sub(r"[^\d]", "", raw_phone or "")
    if len(digits) < 6:
        raise ValueError("Phone number must contain at least 6 digits")
    return digits


@dataclass
class OtpRecord:
    """Internal representation of an active OTP session."""

    reference_id: str
    phone_number: str
    code_hash: str
    salt: str
    purpose: str
    created_at: datetime
    expires_at: datetime
    max_attempts: int
    attempts_used: int = 0
    is_consumed: bool = False
    verified_at: datetime | None = None


class OtpManager:
    """Thread-safe manager for generating, tracking, and verifying one-time passwords."""

    def __init__(
        self,
        default_expiry_seconds: int = 300,
        code_length: int = 6,
        max_attempts: int = 3,
        cooldown_seconds: int = 60,
    ) -> None:
        self.default_expiry_seconds = default_expiry_seconds
        self.code_length = code_length
        self.max_attempts = max_attempts
        self.cooldown_seconds = cooldown_seconds
        self._records: dict[str, OtpRecord] = {}
        self._lock = threading.Lock()

    def _hash_code(self, code: str, salt: str) -> str:
        """Hash a code with its salt using SHA-256."""
        return hashlib.sha256(f"{salt}:{code}".encode()).hexdigest()

    def _generate_numeric_code(self, length: int) -> str:
        """Generate a cryptographically secure random numeric OTP."""
        return "".join(secrets.choice("0123456789") for _ in range(length))

    def create_otp(
        self,
        phone_number: str,
        purpose: str = "sso_login",
        expiry_seconds: int | None = None,
        bypass_cooldown: bool = False,
    ) -> tuple[str, OtpRecord]:
        """Generate a new OTP, hash it with a random salt, and store the session."""
        normalized = normalize_phone_number(phone_number)
        key = f"{normalized}:{purpose}"
        now = datetime.now(UTC)
        ttl = expiry_seconds if expiry_seconds is not None else self.default_expiry_seconds
        expires_at = now + timedelta(seconds=ttl)

        with self._lock:
            existing = self._records.get(key)
            if existing is not None and not existing.is_consumed and not bypass_cooldown:
                elapsed = (now - existing.created_at).total_seconds()
                if elapsed < self.cooldown_seconds and now < existing.expires_at:
                    wait_seconds = max(1, int(self.cooldown_seconds - elapsed))
                    raise ValueError(
                        f"Rate limited: wait {wait_seconds}s before requesting a new OTP"
                    )

            salt = secrets.token_hex(16)
            code = self._generate_numeric_code(self.code_length)
            code_hash = self._hash_code(code, salt)
            reference_id = str(uuid.uuid4())

            record = OtpRecord(
                reference_id=reference_id,
                phone_number=normalized,
                code_hash=code_hash,
                salt=salt,
                purpose=purpose,
                created_at=now,
                expires_at=expires_at,
                max_attempts=self.max_attempts,
                attempts_used=0,
                is_consumed=False,
                verified_at=None,
            )
            self._records[key] = record

        return code, record

    def verify_otp(
        self,
        phone_number: str,
        code: str,
        purpose: str = "sso_login",
        now: datetime | None = None,
    ) -> OtpVerifyResponse:
        """Verify the user-provided code against active session using constant-time comparison."""
        normalized = normalize_phone_number(phone_number)
        key = f"{normalized}:{purpose}"
        check_time = now or datetime.now(UTC)
        if check_time.tzinfo is None:
            check_time = check_time.replace(tzinfo=UTC)

        with self._lock:
            record = self._records.get(key)
            if record is None:
                return OtpVerifyResponse(
                    success=False,
                    status=OtpStatus.NOT_FOUND,
                    phone_number=normalized,
                    reference_id=None,
                    verified_at=None,
                    message="No active OTP found for this phone number and purpose",
                )

            if record.is_consumed:
                return OtpVerifyResponse(
                    success=False,
                    status=OtpStatus.ALREADY_USED,
                    phone_number=normalized,
                    reference_id=record.reference_id,
                    verified_at=record.verified_at,
                    message="This OTP has already been verified and consumed",
                )

            if check_time > record.expires_at:
                return OtpVerifyResponse(
                    success=False,
                    status=OtpStatus.EXPIRED,
                    phone_number=normalized,
                    reference_id=record.reference_id,
                    verified_at=None,
                    message="The OTP has expired",
                )

            if record.attempts_used >= record.max_attempts:
                return OtpVerifyResponse(
                    success=False,
                    status=OtpStatus.MAX_ATTEMPTS_EXCEEDED,
                    phone_number=normalized,
                    reference_id=record.reference_id,
                    verified_at=None,
                    message="Maximum verification attempts exceeded",
                )

            target_hash = self._hash_code(code.strip(), record.salt)
            if secrets.compare_digest(record.code_hash, target_hash):
                record.is_consumed = True
                record.verified_at = check_time
                return OtpVerifyResponse(
                    success=True,
                    status=OtpStatus.VERIFIED,
                    phone_number=normalized,
                    reference_id=record.reference_id,
                    verified_at=check_time,
                    message="OTP successfully verified",
                )

            record.attempts_used += 1
            if record.attempts_used >= record.max_attempts:
                return OtpVerifyResponse(
                    success=False,
                    status=OtpStatus.MAX_ATTEMPTS_EXCEEDED,
                    phone_number=normalized,
                    reference_id=record.reference_id,
                    verified_at=None,
                    message="Invalid OTP. Maximum attempts reached",
                )

            remaining = record.max_attempts - record.attempts_used
            return OtpVerifyResponse(
                success=False,
                status=OtpStatus.INVALID_CODE,
                phone_number=normalized,
                reference_id=record.reference_id,
                verified_at=None,
                message=f"Invalid OTP code. {remaining} attempt(s) remaining",
            )

    def clear(self) -> None:
        """Clear all OTP sessions."""
        with self._lock:
            self._records.clear()


otp_manager = OtpManager(
    default_expiry_seconds=settings.otp_default_expiry_seconds,
    code_length=settings.otp_code_length,
    max_attempts=settings.otp_max_attempts,
    cooldown_seconds=settings.otp_cooldown_seconds,
)
