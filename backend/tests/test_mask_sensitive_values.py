"""Regression tests for _mask_sensitive_values (settings section masking).

A dropped `return masked` made this helper return None, which broke EVERY
GET /api/settings/section/{name} endpoint with a 500 (SectionResponse.config
requires a dict). These tests guard the return contract and the masking
behavior so navigating settings pages never regresses to "failed to load".
"""
from app.api.settings import _mask_sensitive_values


def test_returns_a_dict_not_none():
    """The helper must return the masked dict, never None."""
    result = _mask_sensitive_values({"total_download_mbps": 100})
    assert result == {"total_download_mbps": 100}


def test_masks_top_level_sensitive_keys():
    result = _mask_sensitive_values({"token": "abc123", "url": "http://x"})
    assert result == {"token": "***REDACTED***", "url": "http://x"}


def test_masks_nested_sensitive_keys():
    """Nested dicts are recursed into and must also come back as dicts."""
    result = _mask_sensitive_values(
        {"plex": {"token": "secret", "name": "Plex"}, "enabled": True}
    )
    assert result == {
        "plex": {"token": "***REDACTED***", "name": "Plex"},
        "enabled": True,
    }


def test_leaves_non_sensitive_values_untouched():
    config = {"interval": 5, "enabled": False, "name": "system"}
    assert _mask_sensitive_values(config) == config


def test_does_not_mutate_input():
    original = {"password": "hunter2", "keep": 1}
    _mask_sensitive_values(original)
    assert original == {"password": "hunter2", "keep": 1}
