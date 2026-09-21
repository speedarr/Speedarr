"""Password hashing and JWT helpers in app.utils.auth (PR #64: passlib -> bcrypt 5, python-jose -> PyJWT)."""
import base64
import json
import time
from datetime import timedelta

import pytest

from app.config import settings
from app.utils.auth import BCRYPT_MAX_BYTES, get_password_hash, validate_new_password, verify_password
from app.utils.auth import create_access_token, decode_access_token

# Hashes produced by passlib 1.7.4 + bcrypt 4.0.1 (the pre-#64 stack) on 2026-09-17. Test strings, not secrets.
# passlib hashed only the first 72 bytes of a long password; the two long vectors pin that contract.
PASSLIB_VECTORS = [
    ("correct horse battery staple", "$2b$12$u4lKtscdhgUemdF9hKqYrusuTSWdb7F0tiatVDmOQaH.znL0U.FSq"),   # 28 bytes
    ("L" * 80, "$2b$12$kK5l39OFwYMhvbKYmckL7ORKM8wrpJ3C4u3VHgfk8AW.Iqq3EfQQ6"),                        # 80 bytes
    ("pässwörd-ünïcödé-" + "ß" * 40, "$2b$12$mseLycr.fBtNwQdrMyCJSet818GXU4bw.Z5Z4cHPWOvKMqrPGm/h."),  # 103 bytes
]

ASCII_TOO_LONG = "Password is too long. Use at most 72 characters."
NON_ASCII_TOO_LONG = ASCII_TOO_LONG + " Accented letters, symbols and emoji count as 2 to 4 characters each."
UNSUPPORTED = "Password contains an unsupported character."


# --- stored hashes from the passlib era keep verifying ---------------------------------------

@pytest.mark.parametrize("password,hashed", PASSLIB_VECTORS)
def test_passlib_era_hashes_verify(password, hashed):
    assert verify_password(password, hashed) is True


@pytest.mark.parametrize("password,hashed", PASSLIB_VECTORS)
def test_passlib_era_hashes_reject_a_different_password(password, hashed):
    # Change the FIRST byte: bytes past 72 never took part in these hashes.
    assert verify_password("x" + password, hashed) is False
    assert verify_password("", hashed) is False


def test_ascii_long_hash_covers_exactly_72_bytes():
    hashed = PASSLIB_VECTORS[1][1]
    assert verify_password("L" * 72, hashed) is True
    assert verify_password("L" * 73, hashed) is True   # anything past byte 72 is ignored, as passlib did
    assert verify_password("L" * 71, hashed) is False


def test_multibyte_long_hash_covers_exactly_72_bytes():
    hashed = PASSLIB_VECTORS[2][1]
    prefix = "pässwörd-ünïcödé-"
    assert len(prefix.encode("utf-8")) == 23
    assert verify_password(prefix + "ß" * 25, hashed) is True    # 73 bytes; byte 72 is half of the 25th ß
    assert verify_password(prefix + "ß" * 24, hashed) is False   # 71 bytes


# --- new hashes -------------------------------------------------------------------------------

def test_new_hash_format_and_round_trip():
    first = get_password_hash("hunter2!")
    second = get_password_hash("hunter2!")
    assert first.startswith("$2b$12$") and len(first) == 60
    assert first != second                       # fresh salt per call
    assert verify_password("hunter2!", first) is True
    assert verify_password("hunter2!", second) is True
    assert verify_password("hunter2?", first) is False


def test_exactly_72_bytes_is_accepted():
    ascii72 = "a" * 72
    multibyte72 = "ß" * 36
    assert len(ascii72.encode("utf-8")) == 72 and len(multibyte72.encode("utf-8")) == 72
    validate_new_password(ascii72)
    validate_new_password(multibyte72)
    assert verify_password(ascii72, get_password_hash(ascii72)) is True
    assert verify_password(multibyte72, get_password_hash(multibyte72)) is True


def test_73_ascii_bytes_rejected_with_character_message():
    with pytest.raises(ValueError) as exc:
        get_password_hash("a" * 73)
    assert str(exc.value) == ASCII_TOO_LONG


def test_multibyte_over_72_bytes_rejected_with_explanation():
    with pytest.raises(ValueError) as exc:
        get_password_hash("ß" * 37)    # 37 characters, 74 bytes
    assert str(exc.value) == NON_ASCII_TOO_LONG


def test_nul_byte_rejected():
    with pytest.raises(ValueError) as exc:
        get_password_hash("abc\x00def")
    assert str(exc.value) == UNSUPPORTED


def test_lone_surrogate_rejected_with_unsupported_message():
    with pytest.raises(ValueError) as exc:
        get_password_hash("abc\ud800def")
    assert str(exc.value) == UNSUPPORTED          # never the codec's own message
    assert verify_password("abc\ud800def", PASSLIB_VECTORS[0][1]) is False


def test_bcrypt_max_bytes_constant():
    assert BCRYPT_MAX_BYTES == 72


# --- verify_password never raises -------------------------------------------------------------

@pytest.mark.parametrize(
    "hashed",
    [None, "", "not-a-hash", "$2b$12$tooShort", PASSLIB_VECTORS[0][1][:20], "$2b$12$" + "ü" * 53],
)
def test_verify_never_raises_on_a_bad_hash(hashed):
    assert verify_password("anything", hashed) is False


def test_verify_never_raises_on_nul_or_over_long_input():
    hashed = PASSLIB_VECTORS[0][1]
    assert verify_password("a\x00b", hashed) is False
    assert verify_password("x" * 500, hashed) is False


# --- JWT session tokens ------------------------------------------------------------------------

VECTOR_SECRET = "speedarr-test-vector-secret-not-a-real-key"
# Minted by python-jose 3.5.0 on 2026-09-17 with VECTOR_SECRET, HS256, {"sub": "vector-user", "user_id": 7, "exp": ...}.
JOSE_LIVE = (  # exp 4102444800 = 2100-01-01
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
    "eyJzdWIiOiJ2ZWN0b3ItdXNlciIsInVzZXJfaWQiOjcsImV4cCI6NDEwMjQ0NDgwMH0."
    "Lu9u_LpvfaYgsc2nih7tqTxTb3S52s9bWQ5a-7tkWas"
)
JOSE_EXPIRED = (  # exp 946684800 = 2000-01-01
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
    "eyJzdWIiOiJ2ZWN0b3ItdXNlciIsInVzZXJfaWQiOjcsImV4cCI6OTQ2Njg0ODAwfQ."
    "b2_ITuZCmhs4ibgKLpUE-EjlIUYz4NK08Cbs3kDN0Y8"
)


def _b64(obj) -> str:
    return base64.urlsafe_b64encode(json.dumps(obj, separators=(",", ":")).encode()).rstrip(b"=").decode()


@pytest.fixture
def vector_secret(monkeypatch):
    monkeypatch.setattr(settings.auth, "secret_key", VECTOR_SECRET)
    monkeypatch.setattr(settings.auth, "session_timeout", 3600)
    return VECTOR_SECRET


def test_token_round_trip_uses_session_timeout(vector_secret):
    token = create_access_token({"sub": "u", "user_id": 3})
    assert isinstance(token, str)
    payload = decode_access_token(token)
    assert payload["sub"] == "u" and payload["user_id"] == 3
    assert isinstance(payload["exp"], int)
    now = int(time.time())
    assert now + 3500 <= payload["exp"] <= now + 3700


def test_explicit_expiry_and_expired_token(vector_secret):
    token = create_access_token({"sub": "u"}, expires_delta=timedelta(seconds=120))
    assert int(time.time()) + 100 <= decode_access_token(token)["exp"] <= int(time.time()) + 140
    assert decode_access_token(create_access_token({"sub": "u"}, expires_delta=timedelta(seconds=-1))) is None


def test_python_jose_tokens_still_decode(vector_secret):
    assert decode_access_token(JOSE_LIVE) == {"sub": "vector-user", "user_id": 7, "exp": 4102444800}
    assert decode_access_token(JOSE_EXPIRED) is None


def test_wrong_secret_rejected(vector_secret, monkeypatch):
    token = create_access_token({"sub": "u"})
    monkeypatch.setattr(settings.auth, "secret_key", "a-different-secret-that-is-at-least-32-bytes-long")
    assert decode_access_token(token) is None


def test_tampered_payload_rejected(vector_secret):
    header, payload, signature = create_access_token({"sub": "u", "user_id": 3}).split(".")
    claims = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
    claims["user_id"] = 999
    assert decode_access_token(f"{header}.{_b64(claims)}.{signature}") is None


@pytest.mark.parametrize("token", ["", "garbage", "a.b", "a.b.c", None])
def test_garbage_tokens_rejected(vector_secret, token):
    assert decode_access_token(token) is None


def test_unsigned_alg_none_rejected(vector_secret):
    header = _b64({"alg": "none", "typ": "JWT"})
    payload = _b64({"sub": "u", "exp": 4102444800})
    assert decode_access_token(f"{header}.{payload}.") is None


def test_algorithm_header_swap_rejected(vector_secret):
    _, payload, signature = create_access_token({"sub": "u"}).split(".")
    header = _b64({"alg": "RS256", "typ": "JWT"})
    assert decode_access_token(f"{header}.{payload}.{signature}") is None
