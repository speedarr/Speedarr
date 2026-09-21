"""Path containment for the SPA catch-all route.

The catch-all in app.main serves files from the frontend build directory and falls
back to index.html for client-side routes. These helpers decide which file (if any)
a request may be served. The rule mirrors starlette's StaticFiles.lookup_path, which
already protects the /assets mount: absolute paths are refused, the joined path is
resolved (following symlinks and collapsing parent segments), and the result must
still lie under the static root.
"""
from pathlib import Path


def resolve_static_file(static_root: Path, requested_path: str) -> Path | None:
    """Return the file under ``static_root`` that ``requested_path`` names, or ``None``.

    ``None`` when the path is absolute, escapes the root after resolving symlinks and
    parent segments, contains a NUL byte, hits a symlink loop, names a directory, or
    does not exist. Never raises.
    """
    if requested_path.startswith(("/", "\\")):
        return None
    try:
        # The root is resolved here as well, so the helper holds for a relative or
        # unresolved root, not only the pre-resolved one main.py passes.
        root = static_root.resolve()
        candidate = (root / requested_path).resolve()
    except (ValueError, OSError, RuntimeError):
        # ValueError: NUL byte; OSError: unreadable path; RuntimeError: symlink loop
        # (Python 3.11's Path.resolve turns ELOOP into RuntimeError; 3.13 raises OSError).
        return None
    if not candidate.is_relative_to(root):
        return None
    try:
        if not candidate.is_file():
            return None
    except OSError:
        return None
    return candidate


def spa_file_for(static_root: Path, requested_path: str) -> Path:
    """The file to serve for a SPA request: the contained static file, else index.html."""
    return resolve_static_file(static_root, requested_path) or static_root / "index.html"
