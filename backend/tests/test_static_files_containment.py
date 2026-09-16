"""Containment rules for the SPA catch-all file lookup (app.utils.static_files).

The catch-all route in app.main is only defined when a ./static directory exists,
which the test container does not have, so the rules are tested through the pure
helper. Every case that must not be served returns None; the route then falls back
to index.html.
"""
import os
from pathlib import Path

import pytest

from app.utils.static_files import resolve_static_file, spa_file_for


@pytest.fixture
def static_root(tmp_path: Path) -> Path:
    """A fake frontend build next to things that must never be served.

    tmp_path/
      static/            <- the root
        index.html
        speedarr.svg
        assets/app.js
        link.txt -> ../outside.txt   (symlink pointing out of the root)
      static2/x.txt      <- sibling dir whose name has the root's name as a prefix
      outside.txt        <- sibling file
    """
    root = tmp_path / "static"
    (root / "assets").mkdir(parents=True)
    (root / "index.html").write_text("<html>index</html>")
    (root / "speedarr.svg").write_text("<svg/>")
    (root / "assets" / "app.js").write_text("console.log(1)")
    (tmp_path / "outside.txt").write_text("secret")
    sibling = tmp_path / "static2"
    sibling.mkdir()
    (sibling / "x.txt").write_text("sibling")
    os.symlink(tmp_path / "outside.txt", root / "link.txt")
    return root


def test_serves_file_at_root(static_root):
    assert resolve_static_file(static_root, "speedarr.svg") == (static_root / "speedarr.svg").resolve()


def test_serves_nested_file(static_root):
    assert resolve_static_file(static_root, "assets/app.js") == (static_root / "assets" / "app.js").resolve()


@pytest.mark.parametrize(
    "requested",
    ["../outside.txt", "../../etc/hostname", "assets/../../outside.txt", "..", "../"],
)
def test_rejects_parent_segments_that_leave_the_root(static_root, requested):
    # uvicorn decodes %2f and %2e before routing, so "..%2foutside.txt" reaches the
    # route as "../outside.txt"; these strings are what the route actually sees.
    assert resolve_static_file(static_root, requested) is None


def test_parent_segments_that_stay_inside_are_allowed(static_root):
    # Containment is judged on the resolved path, not on the presence of "..".
    assert resolve_static_file(static_root, "assets/../speedarr.svg") == (static_root / "speedarr.svg").resolve()


@pytest.mark.parametrize("requested", ["/etc/hostname", "//etc/hostname", "\\etc\\hostname"])
def test_rejects_absolute_paths(static_root, requested):
    assert resolve_static_file(static_root, requested) is None


def test_rejects_absolute_path_to_a_file_that_exists(static_root, tmp_path):
    outside = tmp_path / "outside.txt"
    assert outside.is_file()
    assert resolve_static_file(static_root, str(outside)) is None


@pytest.mark.parametrize("requested", ["", ".", "assets", "assets/"])
def test_rejects_directories(static_root, requested):
    assert resolve_static_file(static_root, requested) is None


def test_rejects_nul_byte_without_raising(static_root):
    assert resolve_static_file(static_root, "a\x00b") is None
    assert resolve_static_file(static_root, "speedarr.svg\x00") is None


def test_rejects_symlink_pointing_out_of_the_root(static_root):
    assert (static_root / "link.txt").read_text() == "secret"  # the link itself works on disk
    assert resolve_static_file(static_root, "link.txt") is None


def test_rejects_sibling_directory_sharing_the_root_name_prefix(static_root):
    assert resolve_static_file(static_root, "../static2/x.txt") is None


def test_missing_file_is_none(static_root):
    assert resolve_static_file(static_root, "missing.txt") is None


def test_spa_file_for_falls_back_to_index(static_root):
    index = static_root / "index.html"
    assert spa_file_for(static_root, "missing.txt") == index
    assert spa_file_for(static_root, "settings") == index
    assert spa_file_for(static_root, "") == index
    assert spa_file_for(static_root, "../outside.txt") == index
    assert spa_file_for(static_root, "link.txt") == index


def test_spa_file_for_serves_existing_static_file(static_root):
    assert spa_file_for(static_root, "speedarr.svg") == (static_root / "speedarr.svg").resolve()


def test_relative_static_root(static_root, monkeypatch):
    # main.py passes an absolute, already-resolved root; a relative one must behave the same.
    monkeypatch.chdir(static_root.parent)
    assert resolve_static_file(Path("static"), "speedarr.svg") == (static_root / "speedarr.svg").resolve()
    assert resolve_static_file(Path("static"), "../outside.txt") is None


def test_symlink_loop_inside_root_is_none_without_raising(static_root):
    os.symlink(static_root / "loopb", static_root / "loopa")
    os.symlink(static_root / "loopa", static_root / "loopb")
    assert resolve_static_file(static_root, "loopa") is None
    assert resolve_static_file(static_root, "loopa/x") is None
    assert spa_file_for(static_root, "loopa") == static_root / "index.html"


def test_symlink_loop_outside_root_is_none_without_raising(static_root, tmp_path):
    # The loop is reached through "..", i.e. before containment is judged.
    out = tmp_path / "out"
    out.mkdir()
    os.symlink(out / "b", out / "a")
    os.symlink(out / "a", out / "b")
    assert resolve_static_file(static_root, "../out/a") is None
    assert spa_file_for(static_root, "../out/a") == static_root / "index.html"


def test_symlink_inside_root_to_a_file_inside_root_is_served(static_root):
    os.symlink(static_root / "speedarr.svg", static_root / "logo.svg")
    assert resolve_static_file(static_root, "logo.svg") == (static_root / "speedarr.svg").resolve()


def test_backslash_prefix_is_rejected_even_when_such_a_file_exists(static_root):
    # On POSIX a backslash is an ordinary filename character; the guard must still refuse it.
    (static_root / "\\index.html").write_text("not served")
    assert (static_root / "\\index.html").is_file()
    assert resolve_static_file(static_root, "\\index.html") is None


def test_trailing_slash_resolves_to_the_file(static_root):
    # pathlib drops a trailing separator, so "speedarr.svg/" names the file; it is still inside the root.
    assert resolve_static_file(static_root, "speedarr.svg/") == (static_root / "speedarr.svg").resolve()
