"""The OpenAPI description on /docs carries the tagline, not the old Plex-only pitch."""
from app.main import app

TAGLINE = "Smooth streams first, downloads and seeding with what's left"


def test_app_description_is_the_tagline():
    assert app.title == "Speedarr"
    assert app.description == TAGLINE
