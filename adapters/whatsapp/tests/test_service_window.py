"""Tests for the Meta 24-hour customer service window manager."""

from datetime import UTC, datetime, timedelta

from app.service_window import ServiceWindowManager, normalize_phone_number


def test_phone_number_normalization() -> None:
    assert normalize_phone_number("+595 981 123-456") == "595981123456"
    assert normalize_phone_number("+1 (555) 025-4555") == "15550254555"
    assert normalize_phone_number("595981123456") == "595981123456"


def test_service_window_active_lifecycle() -> None:
    mgr = ServiceWindowManager(window_seconds=86400)
    phone = "+595981123456"

    # Initially inactive
    assert not mgr.is_window_active(phone)
    status_initial = mgr.get_window_status(phone)
    assert not status_initial.is_active
    assert status_initial.remaining_seconds == 0

    # Customer sends message
    now = datetime(2026, 10, 12, 12, 0, 0, tzinfo=UTC)
    mgr.record_incoming_message(phone, timestamp=now)

    # Within 24 hours: 1 hour later
    check_time_active = now + timedelta(hours=1)
    assert mgr.is_window_active(phone, current_time=check_time_active)
    status_active = mgr.get_window_status(phone, current_time=check_time_active)
    assert status_active.is_active
    assert status_active.remaining_seconds == 82800  # 23 hours

    # Exactly after 24 hours + 1 second: expired
    check_time_expired = now + timedelta(hours=24, seconds=1)
    assert not mgr.is_window_active(phone, current_time=check_time_expired)
    status_expired = mgr.get_window_status(phone, current_time=check_time_expired)
    assert not status_expired.is_active
    assert status_expired.remaining_seconds == 0


def test_service_window_refresh() -> None:
    mgr = ServiceWindowManager(window_seconds=86400)
    phone = "595981123456"

    t1 = datetime(2026, 10, 12, 10, 0, 0, tzinfo=UTC)
    mgr.record_incoming_message(phone, timestamp=t1)

    # 20 hours later customer sends another message
    t2 = t1 + timedelta(hours=20)
    mgr.record_incoming_message(phone, timestamp=t2)

    # 30 hours after t1 (10 hours after t2): window still active!
    t3 = t1 + timedelta(hours=30)
    assert mgr.is_window_active(phone, current_time=t3)
