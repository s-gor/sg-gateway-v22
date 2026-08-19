from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


@lru_cache
def get_version() -> str:
    path = ROOT / "VERSION"
    if not path.exists():
        return "0.0.0-dev"
    return path.read_text(encoding="utf-8").strip()


@lru_cache
def get_release_manifest() -> dict:
    path = ROOT / "release-manifest.json"
    if not path.exists():
        return {
            "name": "sg-gateway",
            "version": get_version(),
            "channel": "dev",
            "images": {},
        }
    return json.loads(path.read_text(encoding="utf-8"))