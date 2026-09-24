"""Redaction for the Download Logs feature (audit T1-3).

Key/value patterns are generated from the sensitive-field registry's leaf names, so the
redactor can never disagree with the API mask about what is secret. A few forms that are not
config fields (headers, alternative spellings, webhook hosts) are kept as explicit extras.
"""
import re

from app.config import SECRET_LEAF_NAMES

_EXTRA_NAMES = ("api-key", "apikey", "passwd", "secret", "Authorization")
# Excludes '[' as well as ']' so a second pass can't re-enter an already-redacted
# "[REDACTED]" value (without it, the value class would consume "[REDACTED" and leave
# a stray "]" behind, breaking idempotency).
_VALUE = r'[^"\'\s,}\]\[]+'


def _key_value_pattern(name: str) -> re.Pattern:
    return re.compile(rf'({re.escape(name)}["\']?\s*[:=]\s*["\']?){_VALUE}', re.IGNORECASE)


# Bearer and webhook-host forms run FIRST: the generic `Authorization: <value>` pattern would otherwise
# consume the word "Bearer" and leave the token that follows it in place.
_PATTERNS = [
    re.compile(r'(Bearer\s+)[^\s"\']+', re.IGNORECASE),
    re.compile(r'(https://discord\.com/api/webhooks/)[^\s"\']+', re.IGNORECASE),
    re.compile(r'(https://discordapp\.com/api/webhooks/)[^\s"\']+', re.IGNORECASE),
    re.compile(r'(https://[^/]*\.webhook\.office\.com/)[^\s"\']+', re.IGNORECASE),
    re.compile(r'(https://hooks\.slack\.com/)[^\s"\']+', re.IGNORECASE),
] + [_key_value_pattern(name) for name in sorted(set(SECRET_LEAF_NAMES) | set(_EXTRA_NAMES))]


def redact_log_text(text: str) -> str:
    """Replace every secret value in log text with [REDACTED], keeping the key it belonged to."""
    for pattern in _PATTERNS:
        text = pattern.sub(r"\1[REDACTED]", text)
    return text
