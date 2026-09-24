"""GET /api/settings/history never returns a secret, whatever the stored rows hold (audit T1-1).

After the migration the table holds placeholders; this is the second layer, and it is what protects
a database that somehow skipped the migration. Pattern: test_get_section_handler.py.
"""
import json
from datetime import datetime, timezone
from types import SimpleNamespace

from app.api.settings import get_history
from app.config import REDACTED


def _entry(key, old, new, value_type):
    return SimpleNamespace(key=key, old_value=old, new_value=new, value_type=value_type,
                           changed_at=datetime(2026, 9, 24, tzinfo=timezone.utc), changed_by=1)


class _Manager:
    def __init__(self, entries):
        self.entries = entries

    async def get_config_history(self, db, key=None, limit=100, only_changed=False):
        return self.entries


def _request(entries):
    return SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(config_manager=_Manager(entries))))


async def test_history_masks_json_and_scalar_secrets_and_passes_markers_through():
    entries = [
        _entry("download_clients", None, json.dumps([{"id": "qb", "password": "AUDITMARK-qb", "url": "u"}]), "json"),
        _entry("download_clients", json.dumps([{"id": "qb", "password": "gAAAAcipher"}]), "[DELETED]", "json"),
        _entry("snmp.community", "AUDITMARK-old", "AUDITMARK-new", "string"),
        _entry("snmp.host", "a", "b", "string"),
    ]
    out = await get_history(key=None, limit=100, only_changed=False, request=_request(entries),
                            db=None, current_user=None)
    assert "AUDITMARK" not in json.dumps([e.model_dump() for e in out])
    assert json.loads(out[0].new_value) == [{"id": "qb", "password": REDACTED, "url": "u"}]
    assert out[0].old_value is None
    assert json.loads(out[1].old_value)[0]["password"] == REDACTED and out[1].new_value == "[DELETED]"
    assert (out[2].old_value, out[2].new_value) == (REDACTED, REDACTED)
    assert (out[3].old_value, out[3].new_value) == ("a", "b")
