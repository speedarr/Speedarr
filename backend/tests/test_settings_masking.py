"""Settings responses mask every registry secret, including the four keys T1-3 adds (audit T1-3).

Handlers are called directly with a stand-in Request (pattern: test_get_section_handler.py).
"""
from types import SimpleNamespace

from app.api.settings import get_section, get_download_clients, get_media_servers
from app.config import (
    SpeedarrConfig, BandwidthConfig, DownloadBandwidthConfig, UploadBandwidthConfig,
    StreamBandwidthConfig, SNMPConfig, NotificationsConfig, PushoverNotificationConfig,
    TelegramNotificationConfig, NtfyNotificationConfig, DownloadClientConfig, MediaServerConfig,
    REDACTED,
)


def _bandwidth():
    return BandwidthConfig(
        download=DownloadBandwidthConfig(total_limit=100.0),
        upload=UploadBandwidthConfig(total_limit=50.0),
        streams=StreamBandwidthConfig(),
    )


def _config():
    return SpeedarrConfig(
        bandwidth=_bandwidth(),
        snmp=SNMPConfig(enabled=True, host="router", community="AUDITMARK-snmp"),
        notifications=NotificationsConfig(
            pushover=PushoverNotificationConfig(enabled=True, user_key="AUDITMARK-pu", api_token="AUDITMARK-po"),
            telegram=TelegramNotificationConfig(enabled=True, bot_token="AUDITMARK-bt", chat_id="AUDITMARK-chat"),
            ntfy=NtfyNotificationConfig(enabled=True, topic="AUDITMARK-topic"),
        ),
        download_clients=[
            DownloadClientConfig(id="qb_1", type="qbittorrent", name="qb", url="http://qb", password="AUDITMARK-qb"),
            DownloadClientConfig(id="sab_1", type="sabnzbd", name="sab", url="http://sab", api_key="AUDITMARK-sab"),
        ],
        media_servers=[
            MediaServerConfig(id="p1", name="Plex", url="http://plex", token="AUDITMARK-plex"),
            MediaServerConfig(id="e1", name="Emby", type="emby", url="http://emby", api_key="AUDITMARK-emby"),
        ],
    )


def _request(config):
    return SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(config=config)))


async def test_snmp_section_masks_community_only():
    resp = await get_section("snmp", request=_request(_config()), _auth=None)
    assert resp.config["community"] == REDACTED
    assert resp.config["host"] == "router"


async def test_notifications_section_masks_all_secrets_including_the_three_new_keys():
    resp = await get_section("notifications", request=_request(_config()), _auth=None)
    c = resp.config
    assert c["pushover"]["user_key"] == REDACTED and c["pushover"]["api_token"] == REDACTED
    assert c["telegram"]["chat_id"] == REDACTED and c["telegram"]["bot_token"] == REDACTED
    assert c["ntfy"]["topic"] == REDACTED and c["ntfy"]["server_url"] == "https://ntfy.sh"
    assert "AUDITMARK" not in str(c)


async def test_empty_and_none_secrets_are_not_masked():
    resp = await get_section("notifications", request=_request(SpeedarrConfig(bandwidth=_bandwidth())), _auth=None)
    assert resp.config["discord"]["webhook_url"] is None
    assert resp.config["gotify"]["app_token"] is None
    resp = await get_section("plex", request=_request(SpeedarrConfig(bandwidth=_bandwidth())), _auth=None)
    assert resp.config["token"] == ""


async def test_download_clients_are_masked_per_item():
    resp = await get_download_clients(request=_request(_config()), current_user=None)
    qb, sab = resp.clients
    assert qb["password"] == REDACTED and qb["api_key"] is None and qb["url"] == "http://qb"
    assert sab["api_key"] == REDACTED and sab["password"] is None
    assert "AUDITMARK" not in str(resp.clients)


async def test_media_servers_are_masked_per_item():
    resp = await get_media_servers(request=_request(_config()), current_user=None)
    plex, emby = resp.servers
    assert plex["token"] == REDACTED and plex["api_key"] == "" and plex["url"] == "http://plex"
    assert emby["api_key"] == REDACTED and emby["token"] == ""
    assert "AUDITMARK" not in str(resp.servers)
