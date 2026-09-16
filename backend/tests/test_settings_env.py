"""Settings: the pydantic-settings model_config and nested env parsing (AUTH__* style)."""
from app.config import Settings


def test_settings_model_config_carries_the_env_options():
    cfg = Settings.model_config
    assert cfg["env_file"] == ".env"
    assert cfg["env_file_encoding"] == "utf-8"
    assert cfg["case_sensitive"] is False
    assert cfg["env_nested_delimiter"] == "__"


def test_nested_env_vars_populate_settings(monkeypatch):
    monkeypatch.setenv("AUTH__SECRET_KEY", "k" * 64)
    monkeypatch.setenv("AUTH__SESSION_TIMEOUT", "120")
    monkeypatch.setenv("PORT", "9595")
    monkeypatch.setenv("DEBUG", "true")
    settings = Settings()
    assert settings.auth.secret_key == "k" * 64
    assert settings.auth.session_timeout == 120
    assert settings.port == 9595
    assert settings.debug is True
