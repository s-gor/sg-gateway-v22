from __future__ import annotations

import json
import os
import re
import subprocess
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from typing import Any

from app.xray.profiles import XRAY_MINIMUM_VERSION


GITHUB_API = "https://api.github.com/repos/XTLS/Xray-core"
CACHE_TTL_SECONDS = 300
_VERSION_RE = re.compile(r"^(?:v)?(\d+(?:\.\d+){1,3})")
_CACHE: tuple[float, dict[str, Any]] | None = None


@dataclass(frozen=True)
class XrayRelease:
    channel: str
    version: str
    tag: str
    published_at: str
    prerelease: bool
    html_url: str


class XrayUpdateError(RuntimeError):
    pass


def version_key(value: str) -> tuple[int, ...]:
    match = _VERSION_RE.match(str(value or "").strip())
    if not match:
        return ()
    return tuple(int(part) for part in match.group(1).split("."))


def compare_versions(left: str, right: str) -> int:
    left_key = version_key(left)
    right_key = version_key(right)
    if not left_key or not right_key:
        raise ValueError(f"Некорректная версия Xray: {left!r} / {right!r}")
    width = max(len(left_key), len(right_key))
    left_key += (0,) * (width - len(left_key))
    right_key += (0,) * (width - len(right_key))
    return (left_key > right_key) - (left_key < right_key)


def installed_xray_version() -> str:
    binary = os.getenv("SG_GATEWAY_XRAY_BINARY", "/usr/local/bin/xray")
    try:
        result = subprocess.run(
            [binary, "version"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    lines = (result.stdout or result.stderr or "").splitlines()
    if result.returncode != 0 or not lines:
        return ""
    parts = lines[0].split()
    if len(parts) < 2:
        return ""
    return parts[1].lstrip("v")


def _request_json(url: str, timeout: float = 6.0) -> Any:
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "SG-Gateway-Xray-Updater",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except (OSError, urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError) as exc:
        raise XrayUpdateError(f"Не удалось получить список релизов Xray: {exc}") from exc


def _release(payload: dict[str, Any], channel: str) -> XrayRelease:
    tag = str(payload.get("tag_name") or "").strip()
    version = tag.lstrip("v")
    if not version_key(version):
        raise XrayUpdateError(f"GitHub вернул некорректный тег Xray: {tag or 'пусто'}")
    return XrayRelease(
        channel=channel,
        version=version,
        tag=tag or f"v{version}",
        published_at=str(payload.get("published_at") or payload.get("created_at") or ""),
        prerelease=bool(payload.get("prerelease")),
        html_url=str(payload.get("html_url") or ""),
    )


def _fetch_releases() -> tuple[XrayRelease, XrayRelease | None]:
    stable_payload = _request_json(f"{GITHUB_API}/releases/latest")
    if not isinstance(stable_payload, dict):
        raise XrayUpdateError("GitHub не вернул стабильный релиз Xray")
    stable = _release(stable_payload, "stable")

    releases_payload = _request_json(f"{GITHUB_API}/releases?per_page=30")
    if not isinstance(releases_payload, list):
        raise XrayUpdateError("GitHub не вернул список предварительных релизов Xray")
    candidates: list[XrayRelease] = []
    for item in releases_payload:
        if not isinstance(item, dict) or item.get("draft") or not item.get("prerelease"):
            continue
        try:
            candidates.append(_release(item, "prerelease"))
        except XrayUpdateError:
            continue
    prerelease = max(candidates, key=lambda item: version_key(item.version), default=None)
    return stable, prerelease


def _channel_state(installed: str, release: XrayRelease | None) -> dict[str, Any]:
    if release is None:
        return {
            "release": None,
            "state": "unavailable",
            "can_install": False,
            "message": "Канал временно недоступен.",
        }
    if not installed:
        return {
            "release": asdict(release),
            "state": "available",
            "can_install": True,
            "message": f"Можно установить Xray v{release.version}.",
        }
    comparison = compare_versions(release.version, installed)
    if comparison > 0:
        return {
            "release": asdict(release),
            "state": "available",
            "can_install": True,
            "message": f"Доступно обновление с v{installed} до v{release.version}.",
        }
    if comparison == 0:
        return {
            "release": asdict(release),
            "state": "current",
            "can_install": False,
            "message": f"Установлена актуальная версия этого канала: v{installed}.",
        }
    return {
        "release": asdict(release),
        "state": "blocked",
        "can_install": False,
        "message": (
            f"Установленная v{installed} новее версии канала v{release.version}. "
            "Понижение заблокировано."
        ),
    }


def overview(*, refresh: bool = False) -> dict[str, Any]:
    global _CACHE
    now = time.monotonic()
    installed = installed_xray_version()
    if not refresh and _CACHE and now - _CACHE[0] < CACHE_TTL_SECONDS:
        cached = dict(_CACHE[1])
        cached["installed"] = installed
        cached["stable"] = _channel_state(installed, _release(cached["stable_payload"], "stable"))
        pre_payload = cached.get("prerelease_payload")
        cached["prerelease"] = _channel_state(
            installed,
            _release(pre_payload, "prerelease") if isinstance(pre_payload, dict) else None,
        )
        return cached

    try:
        stable, prerelease = _fetch_releases()
        stable_payload = {
            "tag_name": stable.tag,
            "published_at": stable.published_at,
            "prerelease": stable.prerelease,
            "html_url": stable.html_url,
        }
        prerelease_payload = (
            {
                "tag_name": prerelease.tag,
                "published_at": prerelease.published_at,
                "prerelease": prerelease.prerelease,
                "html_url": prerelease.html_url,
            }
            if prerelease
            else None
        )
        result = {
            "installed": installed,
            "minimum": XRAY_MINIMUM_VERSION,
            "checked": True,
            "error": "",
            "stable_payload": stable_payload,
            "prerelease_payload": prerelease_payload,
            "stable": _channel_state(installed, stable),
            "prerelease": _channel_state(installed, prerelease),
        }
        _CACHE = (now, result)
        return dict(result)
    except XrayUpdateError as exc:
        return {
            "installed": installed,
            "minimum": XRAY_MINIMUM_VERSION,
            "checked": False,
            "error": str(exc),
            "stable_payload": None,
            "prerelease_payload": None,
            "stable": _channel_state(installed, None),
            "prerelease": _channel_state(installed, None),
        }
