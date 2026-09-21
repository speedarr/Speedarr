"""SQLite connect-time pragmas (issue #88).

``set_sqlite_pragma`` was gated on ``isinstance(dbapi_conn, sqlite3.Connection)``,
which is False for SQLAlchemy's aiosqlite adapter, so the live database ran in
delete journal mode with foreign keys off. These tests attach the real handler
to a temporary FILE database: an in-memory one answers ``journal_mode`` with
``memory`` whatever it is asked for.
"""
import sqlite3
from contextlib import contextmanager

import pytest
from loguru import logger
from sqlalchemy import event, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

import app.models  # noqa: F401  (registers every table on Base.metadata)
import app.database
from app.database import (
    Base,
    engine as app_engine,
    init_db,
    log_sqlite_mode,
    set_sqlite_pragma,
    sqlite_mode,
)
from app.models.user import APIToken

EXPECTED = {"journal_mode": "wal", "foreign_keys": 1, "busy_timeout": 5000, "synchronous": 1}


def file_engine(tmp_path, with_handler=True):
    eng = create_async_engine(f"sqlite+aiosqlite:///{tmp_path}/t.db", poolclass=NullPool)
    if with_handler:
        event.listen(eng.sync_engine, "connect", set_sqlite_pragma)
    return eng


async def pragmas(conn):
    return {p: (await conn.execute(text(f"PRAGMA {p}"))).scalar() for p in EXPECTED}


async def test_handler_puts_a_file_database_in_wal_with_foreign_keys_on(tmp_path):
    eng = file_engine(tmp_path)
    try:
        async with eng.connect() as conn:
            first = await pragmas(conn)
        async with eng.connect() as conn:  # NullPool: a brand-new DBAPI connection
            second = await pragmas(conn)
    finally:
        await eng.dispose()
    assert first == EXPECTED
    assert second == EXPECTED


async def test_wal_mode_is_persisted_in_the_file(tmp_path):
    eng = file_engine(tmp_path)
    try:
        async with eng.connect() as conn:
            await conn.execute(text("SELECT 1"))
    finally:
        await eng.dispose()
    with sqlite3.connect(tmp_path / "t.db") as raw:
        assert raw.execute("PRAGMA journal_mode").fetchone()[0] == "wal"


def test_app_engine_has_the_handler_attached():
    assert event.contains(app_engine.sync_engine, "connect", set_sqlite_pragma)


async def test_dangling_api_token_user_id_is_rejected(tmp_path):
    eng = file_engine(tmp_path)
    try:
        async with eng.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        async with async_sessionmaker(eng)() as session:
            session.add(APIToken(user_id=4242, token="x" * 64, name="orphan"))
            with pytest.raises(IntegrityError):
                await session.commit()
    finally:
        await eng.dispose()


async def test_control_without_the_handler_the_same_insert_is_accepted(tmp_path):
    """SQLite's own default is foreign_keys=0; the enforcement must come from the handler."""
    eng = file_engine(tmp_path, with_handler=False)
    try:
        async with eng.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        async with async_sessionmaker(eng)() as session:
            session.add(APIToken(user_id=4242, token="x" * 64, name="orphan"))
            await session.commit()
    finally:
        await eng.dispose()


@contextmanager
def captured_logs():
    records = []
    sink = logger.add(lambda m: records.append(m.record), level="DEBUG")
    try:
        yield records
    finally:
        logger.remove(sink)


async def test_sqlite_mode_reports_the_effective_settings(tmp_path):
    eng = file_engine(tmp_path)
    try:
        assert await sqlite_mode(eng) == {"journal_mode": "wal", "foreign_keys": 1, "synchronous": 1}
    finally:
        await eng.dispose()


def test_log_sqlite_mode_logs_one_info_line_when_wal_is_in_effect():
    with captured_logs() as records:
        log_sqlite_mode({"journal_mode": "wal", "foreign_keys": 1, "synchronous": 1})
    assert [(r["level"].name, r["message"]) for r in records] == [
        ("INFO", "SQLite journal_mode=wal foreign_keys=on synchronous=normal")
    ]


def test_log_sqlite_mode_warns_when_wal_did_not_take():
    with captured_logs() as records:
        log_sqlite_mode({"journal_mode": "delete", "foreign_keys": 1, "synchronous": 2})
    assert len(records) == 1
    assert records[0]["level"].name == "WARNING"
    assert "journal_mode=delete" in records[0]["message"]
    assert "synchronous=full" in records[0]["message"]


async def test_init_db_logs_the_effective_mode(tmp_path, monkeypatch):
    eng = file_engine(tmp_path)
    monkeypatch.setattr(app.database, "engine", eng)
    try:
        with captured_logs() as records:
            await init_db()
    finally:
        await eng.dispose()
    lines = [r["message"] for r in records if r["message"].startswith("SQLite journal_mode=")]
    assert lines == ["SQLite journal_mode=wal foreign_keys=on synchronous=normal"]


async def test_checkpoint_wal_folds_pending_frames_and_truncates_the_log(tmp_path):
    from app.database import checkpoint_wal

    eng = file_engine(tmp_path)
    try:
        async with eng.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        # A connection that has read the WAL-mode file keeps the -wal alive between
        # NullPool operations (SQLite deletes it when the last connection closes).
        keeper = await eng.connect()
        await keeper.execute(text("SELECT count(*) FROM users"))
        try:
            async with eng.begin() as conn:
                await conn.execute(text("INSERT INTO users (username, password_hash) VALUES ('a', 'b')"))
            assert (tmp_path / "t.db-wal").stat().st_size > 0  # frames pending

            result = await checkpoint_wal(eng)

            # TRUNCATE resets the log header before reporting, so success is (busy=0, 0, 0)
            assert result == (0, 0, 0)
            assert (tmp_path / "t.db-wal").stat().st_size == 0
        finally:
            await keeper.close()
    finally:
        await eng.dispose()


async def test_checkpoint_wal_reports_minus_one_on_a_non_wal_database(tmp_path):
    """The pre-fix no-op: SQLite answers (0, -1, -1) when there is no WAL to checkpoint."""
    from app.database import checkpoint_wal

    eng = file_engine(tmp_path, with_handler=False)
    try:
        async with eng.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        assert await checkpoint_wal(eng) == (0, -1, -1)
    finally:
        await eng.dispose()
