"""Row timestamp defaults: naive UTC, no datetime.utcnow (deprecated since Python 3.12)."""
import warnings
from datetime import date, datetime, timezone

import app.models  # noqa: F401  (registers every table on Base.metadata)
from app.database import Base, utcnow


def _callable_defaults():
    """Every callable default / onupdate on every mapped table, as (name, ColumnDefault)."""
    found = []
    for table in Base.metadata.sorted_tables:
        for column in table.columns:
            for kind in ("default", "onupdate"):
                default = getattr(column, kind)
                if default is not None and getattr(default, "is_callable", False):
                    found.append((f"{table.name}.{column.name}.{kind}", default))
    return found


def test_utcnow_is_naive_and_current():
    value = utcnow()
    assert isinstance(value, datetime)
    assert value.tzinfo is None
    reference = datetime.now(timezone.utc).replace(tzinfo=None)
    assert abs((reference - value).total_seconds()) < 5


def test_column_defaults_emit_no_deprecation_and_stay_naive():
    # datetime.utcnow() raises here on Python 3.12+ because DeprecationWarning is an error.
    datetimes = 0
    with warnings.catch_warnings():
        warnings.simplefilter("error", DeprecationWarning)
        for name, default in _callable_defaults():
            value = default.arg(None)
            if isinstance(value, datetime):
                datetimes += 1
                assert value.tzinfo is None, name
            else:
                assert isinstance(value, date), name  # the created_date columns use date.today
    assert datetimes >= 11  # 9 defaults + 2 onupdates; the guard must not pass vacuously
