"""The sensitive-field registry is the one definition of "secret" (audit T1-1 / T1-3).

Every consumer (database codec, API masks, log redactor) reads SENSITIVE_PATHS, which is
derived from the `json_schema_extra=SENSITIVE` marker on the Pydantic fields at import.
"""
import json

import pytest

from app import config as cfg
from app.config import (
    SENSITIVE_PATHS, SECRET_LEAF_NAMES, SECRETS_SCHEMA_VERSION, REDACTED, SpeedarrConfig,
    is_sensitive_key, has_sensitive_leaves, transform_secrets, protect_value, expose_value,
    mask_value, mask_stored, path_to_str, section_model,
)

EXPECTED = {
    "plex.token",
    "media_servers[].token", "media_servers[].api_key",
    "qbittorrent.password", "sabnzbd.api_key",
    "download_clients[].password", "download_clients[].api_key",
    "snmp.community",
    "notifications.discord.webhook_url",
    "notifications.pushover.user_key", "notifications.pushover.api_token",
    "notifications.telegram.bot_token", "notifications.telegram.chat_id",
    "notifications.gotify.app_token",
    "notifications.ntfy.topic",
}

# A field whose name contains one of these must carry the marker or be listed below on purpose.
SECRET_LIKE = ("password", "key", "token", "secret", "webhook", "community", "chat_id", "topic")
ALLOWED_UNMARKED: set = set()


def test_registry_is_exactly_the_fifteen_paths():
    assert {path_to_str(p) for p in SENSITIVE_PATHS} == EXPECTED


def test_schema_version_pins_the_path_count():
    # Marking a new field must come with a version bump so encrypt_stored_secrets re-runs for it.
    assert (SECRETS_SCHEMA_VERSION, len(SENSITIVE_PATHS)) == (1, 15)


def _walk(model_cls, prefix=""):
    for name, field in model_cls.model_fields.items():
        path = f"{prefix}{name}"
        extra = field.json_schema_extra
        marked = isinstance(extra, dict) and bool(extra.get("sensitive"))
        yield path, name, marked
        inner, _ = cfg._unwrap_annotation(field.annotation)
        if inner is not None:
            yield from _walk(inner, path + ".")


def test_every_secret_looking_field_is_marked_or_allowed():
    unmarked = [p for p, name, marked in _walk(SpeedarrConfig)
                if any(s in name for s in SECRET_LIKE) and not marked and p not in ALLOWED_UNMARKED]
    assert unmarked == []


def test_is_sensitive_key_scalar_vs_json_row():
    assert is_sensitive_key("notifications.ntfy.topic")
    assert is_sensitive_key("snmp.community")
    assert is_sensitive_key("plex.token")
    assert not is_sensitive_key("download_clients")
    assert not is_sensitive_key("snmp.host")
    assert has_sensitive_leaves("download_clients")
    assert has_sensitive_leaves("media_servers")
    assert has_sensitive_leaves("notifications")
    assert not has_sensitive_leaves("notifications.ntfy.topic")
    assert not has_sensitive_leaves("bandwidth")


def test_section_model_resolution():
    assert section_model("system") == (cfg.SystemConfig, False)
    assert section_model("qbittorrent") == (cfg.QBittorrentConfig, False)
    assert section_model("download_clients") == (cfg.DownloadClientConfig, True)
    assert section_model("media_servers") == (cfg.MediaServerConfig, True)
    assert section_model("nope") == (None, False)


CLIENTS = [
    {"id": "qb", "password": "p1", "api_key": None, "url": "http://qb", "nested": {"password": "not-a-path"}},
    {"id": "sab", "password": "", "api_key": "k2", "url": "http://sab"},
    {"id": "odd", "password": 123, "api_key": "k3"},
]


def test_walker_touches_only_registered_leaves_and_never_mutates():
    before = json.loads(json.dumps(CLIENTS))
    out = transform_secrets("download_clients", CLIENTS, lambda s: s.upper())
    assert CLIENTS == before
    assert out[0]["password"] == "P1" and out[0]["api_key"] is None
    assert out[0]["nested"] == {"password": "not-a-path"}
    assert out[0]["url"] == "http://qb"
    assert out[1]["password"] == "" and out[1]["api_key"] == "K2"
    assert out[2]["password"] == 123 and out[2]["api_key"] == "K3"


def test_walker_on_scalar_key_empty_list_and_unregistered_key():
    assert transform_secrets("snmp.community", "public", str.upper) == "PUBLIC"
    assert transform_secrets("snmp.community", "", str.upper) == ""
    assert transform_secrets("snmp.community", None, str.upper) is None
    assert transform_secrets("snmp.host", "router", str.upper) == "router"
    assert transform_secrets("media_servers", [], str.upper) == []


def test_protect_expose_round_trip_is_leaf_level():
    stored = protect_value("download_clients", CLIENTS[:2])
    assert stored[0]["password"].startswith("gAAAA")
    assert stored[0]["url"] == "http://qb"
    assert stored[1]["password"] == ""
    assert expose_value("download_clients", stored) == CLIENTS[:2]
    token = protect_value("notifications.telegram.chat_id", "12345")
    assert token != "12345"
    assert expose_value("notifications.telegram.chat_id", token) == "12345"


def test_protect_refuses_the_placeholder():
    with pytest.raises(ValueError, match="placeholder"):
        protect_value("download_clients", [{"id": "qb", "password": REDACTED}])
    with pytest.raises(ValueError, match="placeholder"):
        protect_value("snmp.community", REDACTED)


def test_mask_value_section_and_list():
    assert mask_value("snmp", {"community": "c", "host": "h"}) == {"community": REDACTED, "host": "h"}
    out = mask_value("notifications", {
        "pushover": {"user_key": "u", "api_token": "t", "priority": 0},
        "telegram": {"bot_token": "", "chat_id": "c"},
        "ntfy": {"topic": "top", "server_url": "https://ntfy.sh"},
    })
    assert out["pushover"] == {"user_key": REDACTED, "api_token": REDACTED, "priority": 0}
    assert out["telegram"] == {"bot_token": "", "chat_id": REDACTED}
    assert out["ntfy"] == {"topic": REDACTED, "server_url": "https://ntfy.sh"}
    assert mask_value("media_servers", [{"token": "t", "api_key": "", "url": "u"}]) == [
        {"token": REDACTED, "api_key": "", "url": "u"}
    ]


def test_mask_stored_variants():
    row = json.dumps([{"id": "qb", "password": "p"}])
    assert json.loads(mask_stored("download_clients", row, "json")) == [{"id": "qb", "password": REDACTED}]
    assert mask_stored("plex.token", "gAAAAciphertext", "string") == REDACTED
    assert mask_stored("plex.token", "[DELETED]", "string") == "[DELETED]"
    assert mask_stored("plex.token", None, "string") is None
    assert mask_stored("plex.token", "", "string") == ""
    assert mask_stored("plex.token", "None", "string") == "None"
    assert mask_stored("download_clients", "[DELETED]", "json") == "[DELETED]"
    assert mask_stored("download_clients", "{not json", "json") == "{not json"
    assert mask_stored("snmp.host", "router", "string") == "router"


def test_secret_leaf_names_feed_the_redactor():
    assert set(SECRET_LEAF_NAMES) == {
        "password", "api_key", "token", "community", "user_key", "chat_id", "topic",
        "webhook_url", "api_token", "bot_token", "app_token",
    }


def test_looks_like_fernet_token():
    from app.config import looks_like_fernet_token, encrypt_value
    assert looks_like_fernet_token(encrypt_value("x"))
    assert not looks_like_fernet_token("AUDITMARK-plain")
    assert not looks_like_fernet_token("")
    assert not looks_like_fernet_token("gAAAAA-not-base64!!")
    assert not looks_like_fernet_token(None)
