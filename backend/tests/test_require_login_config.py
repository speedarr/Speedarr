"""require_login flag on SystemConfig (issue #44).

The flag must default to False (public) and round-trip through model_dump()
so it persists via the generic settings save/load with no settings.py change.
"""
from app.config import SystemConfig


def test_require_login_defaults_false():
    assert SystemConfig().require_login is False


def test_require_login_can_be_enabled():
    assert SystemConfig(require_login=True).require_login is True


def test_require_login_roundtrips_through_model_dump():
    dumped = SystemConfig(require_login=True).model_dump()
    assert dumped["require_login"] is True
    assert SystemConfig(**dumped).require_login is True
