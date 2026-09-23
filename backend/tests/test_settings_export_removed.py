"""The config export endpoint is gone (#105).

GET /api/settings/export returned the whole live configuration as YAML with
every password, token and webhook URL in plaintext, and nothing consumed it.
There is no route, no manager method and nothing left to call.
"""
from app.api.settings import router
from app.services.config_manager import ConfigManager


def test_no_export_route():
    paths = [getattr(r, "path", "") for r in router.routes]
    assert not any(p.endswith("/export") for p in paths), paths


def test_config_manager_has_no_export_method():
    assert not hasattr(ConfigManager, "export_to_yaml")
