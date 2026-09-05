from __future__ import annotations

import hashlib
from functools import lru_cache
from pathlib import Path

from flask import url_for


_STATIC_ROOT = Path(__file__).with_name("static")
_ASSET_SUFFIXES = {".css", ".js"}


def _compute_frontend_asset_revision(static_root: Path) -> str:
    digest = hashlib.sha256()
    assets = sorted(
        path
        for path in static_root.rglob("*")
        if path.is_file() and path.suffix.lower() in _ASSET_SUFFIXES
    )
    for path in assets:
        relative = path.relative_to(static_root).as_posix().encode("utf-8")
        digest.update(relative)
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()[:16]


@lru_cache(maxsize=1)
def _default_frontend_asset_revision() -> str:
    return _compute_frontend_asset_revision(_STATIC_ROOT)


def frontend_asset_revision(static_root: Path | str | None = None) -> str:
    if static_root is None:
        return _default_frontend_asset_revision()
    return _compute_frontend_asset_revision(Path(static_root))


def static_asset(filename: str, *, static_root: Path | str | None = None) -> str:
    return url_for(
        "static",
        filename=filename,
        v=frontend_asset_revision(static_root),
    )
