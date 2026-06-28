"""Server-attribution columns exist on the ORM models."""
from app.models.stream import StreamHistory, ActiveStream
from app.models.bandwidth import BandwidthMetric


def test_stream_history_has_server_columns():
    cols = StreamHistory.__table__.columns.keys()
    assert {"server_id", "server_name", "server_type"} <= set(cols)


def test_active_stream_has_server_columns():
    cols = ActiveStream.__table__.columns.keys()
    assert {"server_id", "server_name", "server_type"} <= set(cols)


def test_bandwidth_metric_has_per_server():
    assert "per_server" in BandwidthMetric.__table__.columns.keys()


def test_bandwidth_metric_has_per_client():
    assert "per_client" in BandwidthMetric.__table__.columns.keys()
