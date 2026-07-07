"""require_auth_if_private dependency + bootstrap endpoint logic (issue #44)."""
import asyncio
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

import app.api.auth as auth_module
from app.api.auth import require_auth_if_private
from app.config import SystemConfig
from tests.conftest import make_config


def _request(config, setup_required=False):
    """Minimal stand-in for a FastAPI Request with app.state."""
    return SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace(config=config, setup_required=setup_required))
    )


def test_gate_allows_when_no_config():
    # Setup in progress (config is None) -> never enforce, never lock out.
    result = asyncio.run(require_auth_if_private(request=_request(None), credentials=None, db=None))
    assert result is None


def test_gate_allows_when_require_login_false():
    config = make_config()  # SystemConfig().require_login defaults False
    result = asyncio.run(require_auth_if_private(request=_request(config), credentials=None, db=None))
    assert result is None


def test_gate_returns_user_when_require_login_true_and_authenticated(monkeypatch):
    config = make_config()
    config.system = SystemConfig(require_login=True)
    sentinel = object()

    async def fake_get_current_user(request, credentials, db):
        return sentinel

    monkeypatch.setattr(auth_module, "get_current_user", fake_get_current_user)
    result = asyncio.run(require_auth_if_private(request=_request(config), credentials="c", db="d"))
    assert result is sentinel


def test_gate_propagates_401_when_require_login_true_and_unauthenticated(monkeypatch):
    config = make_config()
    config.system = SystemConfig(require_login=True)

    async def fake_get_current_user(request, credentials, db):
        raise HTTPException(status_code=401, detail="Not authenticated")

    monkeypatch.setattr(auth_module, "get_current_user", fake_get_current_user)
    with pytest.raises(HTTPException) as exc:
        asyncio.run(require_auth_if_private(request=_request(config), credentials=None, db=None))
    assert exc.value.status_code == 401


from app.api.auth import get_bootstrap


def test_bootstrap_no_config_reports_setup_required_login_false():
    out = asyncio.run(get_bootstrap(request=_request(None)))
    assert out == {"setup_required": True, "require_login": False}


def test_bootstrap_with_config_reports_require_login_true():
    config = make_config()
    config.system = SystemConfig(require_login=True)
    out = asyncio.run(get_bootstrap(request=_request(config)))
    assert out == {"setup_required": False, "require_login": True}


def test_bootstrap_with_config_defaults_require_login_false():
    out = asyncio.run(get_bootstrap(request=_request(make_config())))
    assert out == {"setup_required": False, "require_login": False}
