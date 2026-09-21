"""
Authentication utilities for JWT and password hashing.
"""
from datetime import datetime, timedelta, timezone
from typing import Optional

import bcrypt
import jwt

from app.config import settings

BCRYPT_MAX_BYTES = 72  # bcrypt hashes at most 72 bytes; bcrypt >= 5 raises instead of truncating


def validate_new_password(password: str) -> None:
    """Raise ValueError with a user-facing message when bcrypt cannot hash this password."""
    if "\x00" in password:
        raise ValueError("Password contains an unsupported character.")
    try:
        byte_length = len(password.encode("utf-8"))
    except UnicodeEncodeError:
        raise ValueError("Password contains an unsupported character.") from None
    if byte_length > BCRYPT_MAX_BYTES:
        message = f"Password is too long. Use at most {BCRYPT_MAX_BYTES} characters."
        if not password.isascii():
            message += " Accented letters, symbols and emoji count as 2 to 4 characters each."
        raise ValueError(message)


def get_password_hash(password: str) -> str:
    """Hash a password with bcrypt ($2b$, 12 rounds). Raises ValueError for passwords bcrypt cannot hash."""
    validate_new_password(password)
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("ascii")


def verify_password(plain_password: str, hashed_password: Optional[str]) -> bool:
    """Verify a password against its bcrypt hash. Never raises.

    The input is truncated to 72 bytes because every hash stored before bcrypt 5 was
    computed on the first 72 bytes (passlib / bcrypt 4 truncated silently).
    """
    if not hashed_password:
        return False
    try:
        return bcrypt.checkpw(
            plain_password.encode("utf-8")[:BCRYPT_MAX_BYTES],
            hashed_password.encode("utf-8"),
        )
    except ValueError:
        return False


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Create a JWT access token (HS256 per settings.auth.algorithm)."""
    to_encode = data.copy()

    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(seconds=settings.auth.session_timeout)

    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, settings.auth.secret_key, algorithm=settings.auth.algorithm)


def decode_access_token(token: str) -> Optional[dict]:
    """Decode and verify a JWT access token. Returns None for any invalid or expired token."""
    try:
        return jwt.decode(token, settings.auth.secret_key, algorithms=[settings.auth.algorithm])
    except jwt.PyJWTError:
        return None
