"""Shared fixtures for Speedarr backend tests."""
import pytest
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from app.config import (
    SpeedarrConfig,
    BandwidthConfig,
    DownloadBandwidthConfig,
    UploadBandwidthConfig,
    StreamBandwidthConfig,
)
from app.database import Base
from app.services.decision_engine import DecisionEngine


def make_config(download_total=100.0, upload_total=50.0, dl_min=1.0, ul_min=1.0):
    """Build a minimal valid SpeedarrConfig for decision-engine tests."""
    return SpeedarrConfig(
        bandwidth=BandwidthConfig(
            download=DownloadBandwidthConfig(total_limit=download_total, min_limit_mbps=dl_min),
            upload=UploadBandwidthConfig(total_limit=upload_total, min_limit_mbps=ul_min),
            streams=StreamBandwidthConfig(),
        )
    )


def make_stats():
    """Two idle clients: qbittorrent (upload-capable) and sabnzbd (download-only)."""
    return {
        "qbittorrent_1": {"download_speed": 0.0, "upload_speed": 0.0, "supports_upload": True},
        "sabnzbd_1": {"download_speed": 0.0, "upload_speed": 0.0, "supports_upload": False},
    }


UPLOAD_CAPABLE = ("qbittorrent", "transmission", "deluge")


def stats(download=None, upload=None, errors=()):
    """Build a stats dict. Keys are client ids; upload capability from the id prefix."""
    download = download or {}
    upload = upload or {}
    ids = list(download) + [c for c in upload if c not in download]
    out = {}
    for cid in ids:
        out[cid] = {
            "download_speed": float(download.get(cid, 0.0)),
            "upload_speed": float(upload.get(cid, 0.0)),
            "supports_upload": cid.split("_")[0] in UPLOAD_CAPABLE,
        }
        if cid in errors:
            out[cid]["error"] = "unreachable"
    return out


def run(engine, polls):
    """Feed a list of stats dicts through the engine; return the last decisions."""
    decisions = None
    for poll in polls:
        decisions = engine.calculate_throttle(active_streams=[], download_stats=poll)
    return decisions


def dl(decisions, cid):
    return decisions[cid]["download_limit"]


def ul(decisions, cid):
    return decisions[cid]["upload_limit"]


@pytest.fixture
def make_engine():
    def _make(**kwargs):
        return DecisionEngine(make_config(**kwargs))
    return _make


@pytest.fixture
async def db():
    """In-memory aiosqlite session with the full schema, shared by the config-storage tests."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    Session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with Session() as session:
        yield session
    await engine.dispose()
