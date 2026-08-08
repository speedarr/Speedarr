"""Cooldown gate for threshold notifications (issue #72)."""
from datetime import datetime, timedelta, timezone

import pytest

from app.config import NotificationsConfig
from app.services.notification_service import NotificationService


def make_service(count_threshold=None, bitrate_threshold=None, cooldown=0):
    """NotificationService duck-types its config: a bare NotificationsConfig works."""
    config = NotificationsConfig(
        stream_count_threshold=count_threshold,
        stream_bitrate_threshold=bitrate_threshold,
        threshold_cooldown_minutes=cooldown,
    )
    service = NotificationService(config)
    service.sent = []

    async def fake_notify(event_type, message, data=None):
        service.sent.append(event_type)

    service.notify = fake_notify
    return service


async def test_first_crossing_fires():
    s = make_service(count_threshold=2, cooldown=10)
    await s.check_stream_count_threshold(3)
    assert s.sent == ["stream_count_exceeded"]


async def test_recross_within_window_is_suppressed():
    s = make_service(count_threshold=2, cooldown=10)
    await s.check_stream_count_threshold(3)   # fires, starts window
    await s.check_stream_count_threshold(1)   # dip below resets last-notified
    await s.check_stream_count_threshold(3)   # re-cross inside window
    assert s.sent == ["stream_count_exceeded"]


async def test_refires_after_window_expiry():
    s = make_service(count_threshold=2, cooldown=10)
    await s.check_stream_count_threshold(3)
    s._last_threshold_sent["stream_count_exceeded"] = (
        datetime.now(timezone.utc) - timedelta(minutes=11)
    )
    await s.check_stream_count_threshold(1)
    await s.check_stream_count_threshold(3)
    assert s.sent == ["stream_count_exceeded", "stream_count_exceeded"]


async def test_change_during_cooldown_suppressed_and_state_untouched():
    s = make_service(count_threshold=2, cooldown=10)
    await s.check_stream_count_threshold(3)
    await s.check_stream_count_threshold(4)   # changed count, still in window
    assert s.sent == ["stream_count_exceeded"]
    # suppressed send must NOT update last-notified value state
    assert s._last_notified_stream_count == 3


async def test_event_type_windows_are_independent():
    s = make_service(count_threshold=2, bitrate_threshold=50.0, cooldown=10)
    await s.check_stream_count_threshold(3)
    await s.check_stream_bitrate_threshold(60.0)
    assert s.sent == ["stream_count_exceeded", "stream_bitrate_exceeded"]


async def test_cooldown_zero_preserves_current_behavior():
    s = make_service(count_threshold=2, cooldown=0)
    await s.check_stream_count_threshold(3)
    await s.check_stream_count_threshold(1)
    await s.check_stream_count_threshold(3)
    await s.check_stream_count_threshold(4)   # count change while above also fires today
    assert s.sent == ["stream_count_exceeded"] * 3
