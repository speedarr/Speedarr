"""Verify require_auth_if_private is attached to exactly the right routes (issue #44).

Introspects the assembled FastAPI app so a missed or mis-wired router is caught
without needing an HTTP client or pytest-asyncio. Since FastAPI 0.137 an included
router sits in app.routes as an _IncludedRouter placeholder whose include-time
dependencies are merged per request, so the lookup walks the placeholders'
effective routes instead of expecting a flat list.
"""
import pytest

from app.main import app
from app.api.auth import require_auth_if_private
from fastapi.routing import _IncludedRouter


def _dependency_calls(dependant):
    """Flatten all sub-dependency callables for a route's Dependant."""
    calls = []
    for dep in dependant.dependencies:
        calls.append(dep.call)
        calls.extend(_dependency_calls(dep))
    return calls


def _effective_routes(routes):
    """Yield routes as FastAPI matches them: included routers are placeholders whose
    effective_candidates() carry the routes with the include-time dependencies merged in."""
    for route in routes:
        if isinstance(route, _IncludedRouter):
            yield from _effective_routes(route.effective_candidates())
        else:
            yield route


def _route(path, method):
    for route in _effective_routes(app.routes):
        if getattr(route, "path", None) == path and method in (getattr(route, "methods", None) or set()):
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
