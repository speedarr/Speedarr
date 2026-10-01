"""The login rate limit keys on the connecting address, never on a header the caller sets (audit B1-2).

Before: get_client_ip returned X-Forwarded-For (or X-Real-IP) from any peer, so a fresh header value
per request was a fresh identifier and the limit never engaged; the limiter's dicts also grew one
entry per spoofed identifier with no sweep. uvicorn's proxy-headers middleware is the one place a
forwarded address is honoured, and only from a peer listed in FORWARDED_ALLOW_IPS (loopback by
default), so a reverse proxy keeps per-client limiting by setting that variable.
"""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

from app.api.auth import LoginRequest, get_client_ip, login, login_rate_limiter
from app.models import User
from app.utils.auth import get_password_hash
from app.utils.rate_limit import RateLimiter

PEER_A, PEER_B = "203.0.113.5", "203.0.113.6"


def _request(peer=PEER_A, **headers):
    return SimpleNamespace(headers=headers, client=SimpleNamespace(host=peer, port=40000))


def test_the_helper_returns_the_peer_and_ignores_forwarded_headers():
    assert get_client_ip(_request()) == PEER_A
    assert get_client_ip(_request(**{"X-Forwarded-For": "198.51.100.7"})) == PEER_A
    assert get_client_ip(_request(**{"X-Forwarded-For": "198.51.100.7, 10.0.0.1"})) == PEER_A
    assert get_client_ip(_request(**{"X-Real-IP": "198.51.100.7"})) == PEER_A
    assert get_client_ip(SimpleNamespace(headers={}, client=None)) == ""


@pytest.fixture
async def user(db):
    await login_rate_limiter.clear(PEER_A)
    await login_rate_limiter.clear(PEER_B)
    db.add(User(username="corey", password_hash=get_password_hash("right-password-1234567890"),
                role="admin", is_active=True))
    await db.commit()
    yield
    await login_rate_limiter.clear(PEER_A)
    await login_rate_limiter.clear(PEER_B)


async def _attempt(db, peer, **headers):
    try:
        await login(LoginRequest(username="corey", password="wrong-password"), _request(peer, **headers), db)
    except HTTPException as e:
        return e.status_code
    return 200


async def test_rotating_forwarded_headers_from_one_peer_hit_the_limit(db, user):
    codes = [await _attempt(db, PEER_A, **{"X-Forwarded-For": f"198.51.100.{i}"}) for i in range(8)]
    assert codes == [401] * 5 + [429] * 3


async def test_a_second_peer_has_its_own_bucket(db, user):
    for _ in range(5):
        await _attempt(db, PEER_A)
    assert await _attempt(db, PEER_A) == 429
    assert await _attempt(db, PEER_B) == 401


def test_sweep_drops_stale_identifiers_and_expired_blocks():
    limiter = RateLimiter(max_requests=5, window_seconds=60, block_seconds=300)
    now = datetime.now(timezone.utc)
    limiter._requests["old"] = [(now - timedelta(seconds=120)).timestamp()]
    limiter._requests["fresh"] = [(now - timedelta(seconds=10)).timestamp()]
    limiter._requests["empty"] = []
    limiter._blocked["done"] = now - timedelta(seconds=1)
    limiter._blocked["still"] = now + timedelta(seconds=100)
    limiter._sweep(now)
    assert set(limiter._requests) == {"fresh"}
    assert set(limiter._blocked) == {"still"}


async def test_limiter_state_does_not_grow_with_rotating_identifiers():
    limiter = RateLimiter(max_requests=5, window_seconds=0, block_seconds=300)
    for i in range(50):
        await limiter.is_allowed(f"peer-{i}")
    assert len(limiter._requests) <= 1


async def _client_seen_by(peer, forwarded):
    seen = {}

    async def inner(scope, receive, send):
        seen["client"] = scope["client"]

    middleware = ProxyHeadersMiddleware(inner, trusted_hosts="127.0.0.1")
    scope = {"type": "http", "client": peer, "scheme": "http",
             "headers": [(b"x-forwarded-for", forwarded.encode())]}
    await middleware(scope, None, None)
    return seen["client"][0]


async def test_uvicorn_honours_the_forwarded_address_from_loopback_only():
    # Pins the documented composition: FORWARDED_ALLOW_IPS (default 127.0.0.1) is where trust lives.
    assert await _client_seen_by(("127.0.0.1", 1), "198.51.100.7") == "198.51.100.7"
    assert await _client_seen_by(("10.0.0.9", 1), "198.51.100.7") == "10.0.0.9"
