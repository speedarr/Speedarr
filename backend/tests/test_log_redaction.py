"""The gather-logs redactor covers every registry secret name, not a hand-kept subset (audit T1-3)."""
from app.utils.redaction import redact_log_text

LINES = """
2026-09-24 INFO snmp community=AUDITMARK-snmp host=router
2026-09-24 DEBUG pushover user_key: "AUDITMARK-pu", api_token: "AUDITMARK-po"
2026-09-24 DEBUG telegram {'chat_id': 'AUDITMARK-chat', 'bot_token': 'AUDITMARK-bt'}
2026-09-24 DEBUG ntfy topic=AUDITMARK-topic server_url=https://ntfy.sh
2026-09-24 DEBUG qb password=AUDITMARK-qb api_key=AUDITMARK-sab token=AUDITMARK-plex secret=AUDITMARK-s
2026-09-24 DEBUG headers Authorization: Bearer AUDITMARK-jwt apikey=AUDITMARK-k api-key=AUDITMARK-k2 passwd=AUDITMARK-p
2026-09-24 DEBUG webhook https://discord.com/api/webhooks/AUDITMARK-dc and https://hooks.slack.com/AUDITMARK-sl
2026-09-24 INFO Log level Info (effective INFO)
"""


def test_no_secret_survives_and_plain_text_does():
    out = redact_log_text(LINES)
    assert "AUDITMARK" not in out
    assert "community=[REDACTED]" in out
    assert "topic=[REDACTED]" in out
    assert "'chat_id': '[REDACTED]'" in out
    assert "host=router" in out
    assert "server_url=https://ntfy.sh" in out
    assert "Log level Info (effective INFO)" in out


def test_redaction_is_idempotent():
    once = redact_log_text(LINES)
    assert redact_log_text(once) == once
