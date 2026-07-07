"""Regression tests for the GET /settings/section/{name} handler.

Guards two 500 classes:
  1. A populated section (model) must return its config dict (the `return masked`
     regression that broke every visible settings tab).
  2. An unset (Optional=None) or list-typed section must return {} rather than
     crashing _mask_sensitive_values(None) with AttributeError.
"""
from types import SimpleNamespace

import pytest

from app.api.settings import get_section
from app.config import (
    SpeedarrConfig,
    BandwidthConfig,
    DownloadBandwidthConfig,
    UploadBandwidthConfig,
    StreamBandwidthConfig,
)


def _request_with(config):
    return SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(config=config)))


def _config():
    # qbittorrent/sabnzbd default to None; media_servers defaults to [].
    return SpeedarrConfig(
        bandwidth=BandwidthConfig(
            download=DownloadBandwidthConfig(total_limit=100.0, min_limit_mbps=1.0),
            upload=UploadBandwidthConfig(total_limit=50.0, min_limit_mbps=1.0),
            streams=StreamBandwidthConfig(),
        )
    )


@pytest.mark.asyncio
async def test_populated_model_section_returns_config_dict():
    resp = await get_section("system", request=_request_with(_config()), _auth=None)
    assert isinstance(resp.config, dict)
    assert "update_frequency" in resp.config


@pytest.mark.asyncio
async def test_unset_optional_section_returns_empty_dict():
    # qbittorrent is Optional[...] = None when no client configured.
    resp = await get_section("qbittorrent", request=_request_with(_config()), _auth=None)
    assert resp.config == {}


@pytest.mark.asyncio
async def test_list_typed_section_returns_empty_dict():
    # media_servers is a list; the section endpoint cannot represent it (it has a
    # dedicated /media-servers endpoint) — must not 500.
    resp = await get_section("media_servers", request=_request_with(_config()), _auth=None)
    assert resp.config == {}
