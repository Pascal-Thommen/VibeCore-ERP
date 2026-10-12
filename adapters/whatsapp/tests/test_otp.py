"""Tests for OTP generation, hashing, expiration, and verification logic."""

from datetime import timedelta

import pytest

from app.otp import OtpManager
from app.schemas import OtpStatus


def test_otp_generation_and_successful_verification() -> None:
    mgr = OtpManager(default_expiry_seconds=300, code_length=6, max_attempts=3)
    phone = "+595 981 111 222"

    code, record = mgr.create_otp(phone, purpose="sso_login")

    assert len(code) == 6
    assert code.isdigit()
    assert record.phone_number == "595981111222"
    assert record.purpose == "sso_login"
    assert not record.is_consumed

    # Verify with correct code
    res = mgr.verify_otp(phone, code, purpose="sso_login")
    assert res.success
    assert res.status == OtpStatus.VERIFIED
    assert res.reference_id == record.reference_id

    # Replay protection: cannot verify a consumed code
    res_replay = mgr.verify_otp(phone, code, purpose="sso_login")
    assert not res_replay.success
    assert res_replay.status == OtpStatus.ALREADY_USED


def test_otp_expiration_ttl() -> None:
    mgr = OtpManager(default_expiry_seconds=120, code_length=6)
    phone = "595981333444"

    code, record = mgr.create_otp(phone, expiry_seconds=60)
    now = record.created_at

    # 30 seconds later: still valid
    res_valid = mgr.verify_otp(phone, code, now=now + timedelta(seconds=30))
    assert res_valid.success

    # Reset session for test
    mgr.clear()
    code2, record2 = mgr.create_otp(phone, expiry_seconds=60)
    # 61 seconds later: expired
    res_expired = mgr.verify_otp(phone, code2, now=record2.created_at + timedelta(seconds=61))
    assert not res_expired.success
    assert res_expired.status == OtpStatus.EXPIRED


def test_otp_max_attempts_lockout() -> None:
    mgr = OtpManager(default_expiry_seconds=300, max_attempts=3)
    phone = "595981555666"

    code, _ = mgr.create_otp(phone)

    # Attempt 1: wrong code
    res1 = mgr.verify_otp(phone, "000000")
    assert not res1.success
    assert res1.status == OtpStatus.INVALID_CODE
    assert "2 attempt(s) remaining" in res1.message

    # Attempt 2: wrong code
    res2 = mgr.verify_otp(phone, "111111")
    assert not res2.success
    assert res2.status == OtpStatus.INVALID_CODE
    assert "1 attempt(s) remaining" in res2.message

    # Attempt 3: wrong code -> lockout
    res3 = mgr.verify_otp(phone, "222222")
    assert not res3.success
    assert res3.status == OtpStatus.MAX_ATTEMPTS_EXCEEDED

    # Even if now entering the correct code, lockout persists
    res_locked = mgr.verify_otp(phone, code)
    assert not res_locked.success
    assert res_locked.status == OtpStatus.MAX_ATTEMPTS_EXCEEDED


def test_otp_rate_limiting_cooldown() -> None:
    mgr = OtpManager(default_expiry_seconds=300, cooldown_seconds=60)
    phone = "595981777888"

    mgr.create_otp(phone)

    # Immediate request for same phone must fail with rate limiting error
    with pytest.raises(ValueError, match="Rate limited"):
        mgr.create_otp(phone)

    # Bypass cooldown allows generation
    code2, _ = mgr.create_otp(phone, bypass_cooldown=True)
    assert len(code2) == 6


def test_otp_purpose_isolation() -> None:
    mgr = OtpManager(default_expiry_seconds=300)
    phone = "595981999000"

    code_sso, _ = mgr.create_otp(phone, purpose="sso_login")
    code_reset, _ = mgr.create_otp(phone, purpose="password_reset")

    # Trying to verify sso code under password_reset fails
    res = mgr.verify_otp(phone, code_sso, purpose="password_reset")
    assert not res.success
    assert res.status == OtpStatus.INVALID_CODE

    # Verifying under correct purpose succeeds
    res_sso = mgr.verify_otp(phone, code_sso, purpose="sso_login")
    assert res_sso.success
    assert res_sso.status == OtpStatus.VERIFIED
