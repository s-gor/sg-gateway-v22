from __future__ import annotations

import json
import os
import re
import subprocess
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.maintenance.xray_updates import compare_versions, installed_xray_version, version_key


CACHE_TTL_SECONDS = 300
_CACHE: tuple[float, dict[str, Any]] | None = None
INSTALL_ENV = Path(os.getenv("SG_GATEWAY_INSTALL_ENV", "/etc/sg-gateway/runtime.env"))


@dataclass(frozen=True)
class CoreSpec:
    engine: str
    title: str
    repo: str
    binary: str


SPECS = (
    CoreSpec("mihomo", "Mihomo", "MetaCubeX/mihomo", "/usr/local/bin/mihomo"),
    CoreSpec("sing-box", "sing-box", "SagerNet/sing-box", "/usr/local/bin/sing-box"),
    CoreSpec("wgcf", "WARP / wgcf-cli", "ArchiveNetwork/wgcf-cli", "/usr/local/bin/wgcf-cli"),
)

_VERSION_RE = re.compile(r"(?:^|\s)v?(\d+(?:\.\d+){1,3})(?:\s|$)")
_ANSI_ESCAPE_RE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")


class CoreUpdateError(RuntimeError):
    pass


def _headers() -> dict[str, str]:
    return {
        "Accept": "application/vnd.github+json",
        "User-Agent": "SG-Gateway-Core-Updater",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def _request_json(url: str, timeout: float = 8.0) -> Any:
    request = urllib.request.Request(url, headers=_headers())
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except (OSError, urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError) as exc:
        raise CoreUpdateError(str(exc)) from exc


def _parse_version(text: str) -> str:
    clean = _ANSI_ESCAPE_RE.sub("", str(text or ""))
    for line in clean.splitlines():
        match = _VERSION_RE.search(line.strip())
        if match and version_key(match.group(1)):
            return match.group(1)
    return ""


def _version_commands(spec: CoreSpec, binary: str | None = None) -> list[list[str]]:
    executable = binary or spec.binary
    if spec.engine == "mihomo":
        return [[executable, "-v"], [executable, "--version"]]
    if spec.engine == "sing-box":
        return [[executable, "version"], [executable, "--version"]]
    if spec.engine == "wgcf":
        # wgcf-cli releases have used more than one version flag. Probe all
        # harmless forms instead of assuming one CLI spelling.
        return [
            [executable, "version"],
            [executable, "--version"],
            [executable, "-v"],
        ]
    return []


def _install_env_version(spec: CoreSpec) -> str:
    key = {
        "mihomo": "SG_GATEWAY_MIHOMO_VERSION",
        "sing-box": "SG_GATEWAY_SINGBOX_VERSION",
        "wgcf": "SG_GATEWAY_WGCF_VERSION",
    }.get(spec.engine, "")
    if not key:
        return ""
    try:
        for raw in INSTALL_ENV.read_text(encoding="utf-8", errors="replace").splitlines():
            if "=" not in raw or raw.lstrip().startswith("#"):
                continue
            name, value = raw.split("=", 1)
            if name.strip() != key:
                continue
            parsed = _parse_version(value.strip().strip('"\''))
            if parsed:
                return parsed
    except OSError:
        pass
    return ""


def _installed(spec: CoreSpec) -> str:
    path = Path(spec.binary)
    if not path.is_file():
        return ""
    for command in _version_commands(spec):
        try:
            result = subprocess.run(command, capture_output=True, text=True, timeout=6, check=False)
        except (OSError, subprocess.SubprocessError):
            continue
        value = _parse_version((result.stdout or "") + "\n" + (result.stderr or ""))
        # A valid version string is sufficient for a read-only probe even if a
        # particular release returns a non-zero code for that spelling.
        if value:
            return value
    # The installer records pinned runtime versions. This is a safe display
    # fallback when a third-party binary changes its version flag syntax.
    return _install_env_version(spec)


def _release(spec: CoreSpec) -> dict[str, Any]:
    payload = _request_json(f"https://api.github.com/repos/{spec.repo}/releases/latest")
    if not isinstance(payload, dict) or payload.get("draft") or payload.get("prerelease"):
        raise CoreUpdateError("нет стабильного GitHub Release")
    tag = str(payload.get("tag_name") or "").strip()
    version = tag.lstrip("v")
    if not version_key(version):
        raise CoreUpdateError(f"некорректный release tag: {tag or 'пусто'}")
    return {
        "version": version,
        "tag": tag or f"v{version}",
        "published_at": str(payload.get("published_at") or payload.get("created_at") or ""),
        "html_url": str(payload.get("html_url") or ""),
    }


def _state(spec: CoreSpec) -> dict[str, Any]:
    installed = _installed(spec)
    try:
        release = _release(spec)
    except CoreUpdateError as exc:
        return {
            "engine": spec.engine,
            "title": spec.title,
            "installed": installed,
            "release": None,
            "state": "unavailable",
            "can_install": False,
            "message": f"Проверка недоступна: {exc}",
        }
    target = str(release["version"])
    if not installed:
        state, can_install, message = "available", True, f"Можно установить v{target}."
    else:
        comparison = compare_versions(target, installed)
        if comparison > 0:
            state, can_install, message = "available", True, f"Доступно обновление v{installed} → v{target}."
        elif comparison == 0:
            state, can_install, message = "current", False, f"Установлена актуальная v{installed}."
        else:
            state, can_install, message = "blocked", False, f"Установленная v{installed} новее stable v{target}; понижение запрещено."
    return {
        "engine": spec.engine,
        "title": spec.title,
        "installed": installed,
        "release": release,
        "state": state,
        "can_install": can_install,
        "message": message,
    }


def _awg_state() -> dict[str, Any]:
    env_path = Path(os.getenv("SG_GATEWAY_INSTALL_ENV", "/etc/sg-gateway/runtime.env"))
    values: dict[str, str] = {}
    try:
        for raw in env_path.read_text(encoding="utf-8", errors="replace").splitlines():
            if "=" not in raw or raw.lstrip().startswith("#"):
                continue
            key, value = raw.split("=", 1)
            values[key.strip()] = value.strip().strip('"\'')
    except OSError:
        pass
    tools = values.get("SG_GATEWAY_AWG_TOOLS_VERSION", "")
    kmod = values.get("SG_GATEWAY_AWG_KMOD_VERSION", "")
    label = " / ".join(item for item in (tools, kmod) if item) or "не определена"
    return {
        "engine": "amneziawg",
        "title": "AmneziaWG",
        "installed": label,
        "release": None,
        "state": "managed",
        "can_install": False,
        "message": "Обновляется только совместимой парой tools + kernel module. Автоматический latest намеренно отключён.",
    }


def overview(*, refresh: bool = False) -> dict[str, Any]:
    global _CACHE
    now = time.monotonic()
    if not refresh and _CACHE and now - _CACHE[0] < CACHE_TTL_SECONDS:
        result = dict(_CACHE[1])
        result["xray_installed"] = installed_xray_version()
        return result
    items = [_state(spec) for spec in SPECS]
    items.append(_awg_state())
    result = {
        "checked": True,
        "items": items,
        "xray_installed": installed_xray_version(),
    }
    _CACHE = (now, result)
    return dict(result)
