"""Register / change-password turn an unhashable password into a 400 with a user-facing message (PR #64)."""
import asyncio
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.api.auth import ChangePasswordRequest, RegisterRequest, change_password, register
from app.utils.auth import get_password_hash, verify_password

ASCII_TOO_LONG = "Password is too long. Use at most 72 characters."
NON_ASCII_TOO_LONG = ASCII_TOO_LONG + " Accented letters, symbols and emoji count as 2 to 4 characters each."


class FakeDB:
    """Just enough AsyncSession for these two routes: execute/scalars/all, add, commit, refresh."""

    def __init__(self, users=()):
        self.users = list(users)
        self.added = []
        self.commits = 0

    async def execute(self, _stmt):
        rows = self.users
        return SimpleNamespace(
            scalars=lambda: SimpleNamespace(all=lambda: rows),
            scalar_one_or_none=lambda: rows[0] if rows else None,
        )

    def add(self, obj):
        self.added.append(obj)

    async def commit(self):
        self.commits += 1

    async def refresh(self, obj):
        obj.id = 1

    async def flush(self):
        pass


def _user(password):
    return SimpleNamespace(id=1, username="admin", password_hash=get_password_hash(password), role="admin", is_active=True)


def _change(user, db, current, new):
    return asyncio.run(
        change_password(ChangePasswordRequest(current_password=current, new_password=new), current_user=user, db=db)
    )


def test_change_password_rejects_73_byte_password():
    user = _user("old-password")
    before = user.password_hash
    db = FakeDB()
    with pytest.raises(HTTPException) as exc:
        _change(user, db, "old-password", "a" * 73)
    assert exc.value.status_code == 400
    assert exc.value.detail == ASCII_TOO_LONG
    assert user.password_hash == before
    assert db.commits == 0


def test_change_password_rejects_multibyte_over_72_bytes_with_explanation():
    user = _user("old-password")
    with pytest.raises(HTTPException) as exc:
        _change(user, FakeDB(), "old-password", "ß" * 37)
    assert exc.value.status_code == 400
    assert exc.value.detail == NON_ASCII_TOO_LONG


def test_change_password_wrong_current_password_is_still_400():
    user = _user("old-password")
    with pytest.raises(HTTPException) as exc:
        _change(user, FakeDB(), "nope", "new-password")
    assert exc.value.status_code == 400
    assert exc.value.detail == "Current password is incorrect"


def test_change_password_happy_path_rehashes_and_commits():
    user = _user("old-password")
    db = FakeDB()
    result = _change(user, db, "old-password", "new-password")
    assert result == {"message": "Password changed successfully"}
    assert verify_password("new-password", user.password_hash) is True
    assert verify_password("old-password", user.password_hash) is False
    assert db.commits == 1


def test_register_rejects_73_byte_password_before_creating_the_user():
    db = FakeDB(users=[])
    with pytest.raises(HTTPException) as exc:
        asyncio.run(register(RegisterRequest(username="admin", password="a" * 73), db=db))
    assert exc.value.status_code == 400
    assert exc.value.detail == ASCII_TOO_LONG
    assert db.added == []
    assert db.commits == 0


def test_register_rejects_multibyte_over_72_bytes_with_explanation():
    with pytest.raises(HTTPException) as exc:
        asyncio.run(register(RegisterRequest(username="admin", password="ß" * 37), db=FakeDB(users=[])))
    assert exc.value.status_code == 400
    assert exc.value.detail == NON_ASCII_TOO_LONG
