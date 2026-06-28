"""id-targeted manual throttle decision builder."""
import asyncio
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.api.control import ClientThrottle, ManualThrottleRequest, build_throttle_decisions, manual_throttle


def test_builds_decisions_keyed_by_id():
    clients = [ClientThrottle(client_id="qbittorrent_1", download_limit=50, upload_limit=10)]
    decisions = build_throttle_decisions(clients, {"qbittorrent_1", "qbittorrent_2"}, "manual")
    assert decisions == {
        "qbittorrent_1": {"action": "throttle", "download_limit": 50,
                          "upload_limit": 10, "reason": "manual"}
    }


def test_unknown_id_raises():
    with pytest.raises(ValueError):
        build_throttle_decisions([ClientThrottle(client_id="nope")], {"qbittorrent_1"}, "manual")


def test_empty_list_raises():
    with pytest.raises(ValueError):
        build_throttle_decisions([], {"qbittorrent_1"}, "manual")


def _make_request(known_ids):
    """Minimal request stub for manual_throttle route tests."""
    cm = SimpleNamespace(
        clients={cid: object() for cid in known_ids},
    )
    ns = SimpleNamespace(
        app=SimpleNamespace(
            state=SimpleNamespace(
                controller_manager=cm,
                notification_service=SimpleNamespace(notify=lambda *a, **kw: None),
            )
        )
    )
    return ns


def _make_user():
    return SimpleNamespace(username="admin")


def test_route_unknown_id_returns_400_not_500():
    """HTTPException(400) must not be swallowed and re-raised as 500."""
    request = _make_request(known_ids={"qbittorrent_1"})
    body = ManualThrottleRequest(clients=[ClientThrottle(client_id="unknown_client")])
    user = _make_user()
    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(manual_throttle(request, body, user))
    assert exc_info.value.status_code == 400


def test_route_empty_clients_returns_400_not_500():
    """Empty clients list must yield 400, not 500."""
    request = _make_request(known_ids={"qbittorrent_1"})
    body = ManualThrottleRequest(clients=[])
    user = _make_user()
    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(manual_throttle(request, body, user))
    assert exc_info.value.status_code == 400
