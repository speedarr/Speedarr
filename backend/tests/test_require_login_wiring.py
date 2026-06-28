"""Verify require_auth_if_private is attached to exactly the right routes (issue #44).

Introspects the assembled FastAPI app so a missed or mis-wired router is caught
without needing an HTTP client or pytest-asyncio.
"""
import pytest

from app.main import app
from app.api.auth import require_auth_if_private


def _dependency_calls(dependant):
    """Flatten all sub-dependency callables for a route's Dependant."""
    calls = []
    for dep in dependant.dependencies:
        calls.append(dep.call)
        calls.extend(_dependency_calls(dep))
    return calls


def _route(path, method):
    for route in app.routes:
        if getattr(route, "path", None) == path and method in getattr(route, "methods", set()):
            return route
    raise AssertionError(f"route {method} {path} not found")


def _is_gated(path, method):
    return require_auth_if_private in _dependency_calls(_route(path, method).dependant)


GATED = [
    ("/api/status/current", "GET"),
    ("/api/streams/active", "GET"),
    ("/api/streams/history", "GET"),
    ("/api/bandwidth/reservations", "GET"),
    ("/api/decisions/logs", "GET"),
    ("/api/settings/sections", "GET"),
    ("/api/settings/section/{section_name}", "GET"),
]

PUBLIC = [
    ("/api/auth/bootstrap", "GET"),
    ("/api/auth/login", "POST"),
    ("/api/status/version", "GET"),
    ("/api/status/health", "GET"),
]


@pytest.mark.parametrize("path,method", GATED)
def test_gated_routes_carry_the_gate(path, method):
    assert _is_gated(path, method), f"{method} {path} should be gated by require_auth_if_private"


@pytest.mark.parametrize("path,method", PUBLIC)
def test_public_routes_are_not_gated(path, method):
    assert not _is_gated(path, method), f"{method} {path} must NOT carry require_auth_if_private"
