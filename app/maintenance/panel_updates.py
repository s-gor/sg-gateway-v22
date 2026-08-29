from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from app.version import ROOT as APP_ROOT, get_version


GITHUB_REPO = os.getenv("SG_GATEWAY_UPDATE_REPO", "s-gor/sg-gateway-v22").strip() or "s-gor/sg-gateway-v22"
GITHUB_BRANCH = os.getenv("SG_GATEWAY_UPDATE_BRANCH", "stable-02206").strip() or "stable-02206"
GITHUB_API = f"https://api.github.com/repos/{GITHUB_REPO}"
STATE_FILE = Path(os.getenv("SG_GATEWAY_PANEL_UPDATE_STATE", "/var/lib/sg-gateway/updates/panel-state.json"))
CACHE_TTL_SECONDS = 300
_CACHE: tuple[float, dict[str, Any]] | None = None


class PanelUpdateError(RuntimeError):
    pass


def _fingerprint_ignored(relative: Path) -> bool:
    parts = relative.parts
    return (
        ".venv" in parts
        or ".git" in parts
        or ".pytest_cache" in parts
        or "__pycache__" in parts
        or relative.suffix in {".pyc", ".pyo"}
        or ("vendor" in parts and "cores" in parts)
    )


def source_fingerprint(root: Path = APP_ROOT) -> str:
    digest = hashlib.sha256()
    if not root.is_dir():
        return ""
    for path in sorted((item for item in root.rglob("*") if item.is_file()), key=lambda item: item.as_posix()):
        relative = path.relative_to(root)
        if _fingerprint_ignored(relative):
            continue
        digest.update(relative.as_posix().encode("utf-8"))
        digest.update(b"\0")
        try:
            with path.open("rb") as stream:
                for block in iter(lambda: stream.read(1024 * 1024), b""):
                    digest.update(block)
        except OSError:
            return ""
        digest.update(b"\0")
    return digest.hexdigest()


def _headers() -> dict[str, str]:
    return {
        "Accept": "application/vnd.github+json",
        "User-Agent": "SG-Gateway-Panel-Updater",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def _curl_text(url: str, timeout: float) -> str:
    try:
        completed = subprocess.run(
            [
                "curl",
                "-4",
                "-fsSL",
                "--max-time",
                str(max(1, int(timeout))),
                "-A",
                "SG-Gateway-Panel-Updater",
                url,
            ],
            capture_output=True,
            text=True,
            timeout=max(2.0, timeout + 2.0),
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise PanelUpdateError(f"GitHub недоступен: {exc}") from exc
    if completed.returncode != 0:
        detail = (completed.stderr or "").strip()
        raise PanelUpdateError(f"GitHub недоступен через curl: {detail or f'rc={completed.returncode}'}")
    return completed.stdout


def _request_text(url: str, timeout: float = 8.0) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": "SG-Gateway-Panel-Updater"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.read().decode("utf-8")
    except (OSError, urllib.error.URLError, urllib.error.HTTPError, TimeoutError, UnicodeDecodeError) as first_exc:
        try:
            return _curl_text(url, timeout)
        except PanelUpdateError as second_exc:
            raise PanelUpdateError(f"Не удалось получить данные GitHub: {first_exc}; fallback: {second_exc}") from second_exc


def _request_json(url: str, timeout: float = 8.0) -> Any:
    request = urllib.request.Request(url, headers=_headers())
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except (OSError, urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError, UnicodeDecodeError) as first_exc:
        try:
            return json.loads(_curl_text(url, timeout))
        except (PanelUpdateError, json.JSONDecodeError) as second_exc:
            raise PanelUpdateError(f"Не удалось проверить GitHub {GITHUB_BRANCH}: {first_exc}; fallback: {second_exc}") from second_exc


def _latest_channel() -> tuple[str, str, str]:
    # Primary path: GitHub REST API. Fallback: the public Atom feed, which is
    # not subject to the unauthenticated REST API rate-limit bucket.
    try:
        payload = _request_json(f"{GITHUB_API}/commits/{GITHUB_BRANCH}")
        if not isinstance(payload, dict):
            raise PanelUpdateError("GitHub не вернул commit update-channel")
        sha = str(payload.get("sha") or "").strip().lower()
        if len(sha) != 40 or any(ch not in "0123456789abcdef" for ch in sha):
            raise PanelUpdateError("GitHub вернул некорректный SHA commit")
        commit = payload.get("commit") if isinstance(payload.get("commit"), dict) else {}
        author = commit.get("author") if isinstance(commit.get("author"), dict) else {}
        return sha, str(author.get("date") or ""), str(payload.get("html_url") or "")
    except PanelUpdateError:
        atom = _request_text(f"https://github.com/{GITHUB_REPO}/commits/{GITHUB_BRANCH}.atom", timeout=10.0)
        match = re.search(r"Grit::Commit/([0-9a-fA-F]{40})", atom)
        if not match:
            raise PanelUpdateError(f"GitHub {GITHUB_BRANCH} не удалось определить ни через API, ни через Atom feed")
        sha = match.group(1).lower()
        date_match = re.search(r"<updated>([^<]+)</updated>", atom)
        return sha, (date_match.group(1).strip() if date_match else ""), f"https://github.com/{GITHUB_REPO}/commit/{sha}"


def _remote_version(commit: str) -> str:
    value = _request_text(f"https://raw.githubusercontent.com/{GITHUB_REPO}/{commit}/VERSION", timeout=10.0).strip()
    if not value or len(value) > 80:
        raise PanelUpdateError("GitHub VERSION отсутствует или повреждён")
    return value


def _version_key(value: str) -> tuple[int, ...]:
    numbers = re.findall(r"\d+", str(value or ""))
    return tuple(int(item) for item in numbers) if numbers else ()


def _read_state() -> dict[str, Any]:
    try:
        value = json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def overview(*, refresh: bool = False) -> dict[str, Any]:
    global _CACHE
    now = time.monotonic()
    state = _read_state()
    installed_commit = str(state.get("commit") or "").strip().lower()
    recorded_fingerprint = str(state.get("source_fingerprint") or "").strip().lower()
    current_fingerprint = source_fingerprint()
    state_empty = not installed_commit and not recorded_fingerprint
    baseline_valid = bool(
        installed_commit
        and recorded_fingerprint
        and current_fingerprint
        and recorded_fingerprint == current_fingerprint
    )
    installed_version = get_version()

    def _decorate(cached: dict[str, Any]) -> dict[str, Any]:
        cached = dict(cached)
        cached["installed_commit"] = installed_commit
        cached["installed_version"] = installed_version
        cached["source_fingerprint"] = current_fingerprint
        cached["baseline_valid"] = baseline_valid
        cached["bootstrap_allowed"] = False
        latest_commit = str(cached.get("latest_commit") or "")
        latest_version = str(cached.get("latest_version") or "")
        if baseline_valid:
            if installed_commit == latest_commit:
                cached["state"] = "current"
                cached["can_install"] = False
                cached["message"] = "Локальная база уже соответствует проверенному GitHub."
            elif latest_commit:
                cached["state"] = "available"
                cached["can_install"] = True
                cached["message"] = "GitHub содержит новый commit. Можно выполнить безопасное обновление панели."
        elif state_empty and _version_key(latest_version) > _version_key(installed_version):
            cached["state"] = "available"
            cached["can_install"] = True
            cached["bootstrap_allowed"] = True
            cached["message"] = f"Доступна VERSION {latest_version}. Можно выполнить безопасное обновление SG-Gateway."
        else:
            cached["state"] = "uninitialized"
            cached["can_install"] = False
            cached["message"] = (
                "Автоматическое обновление сейчас недоступно. "
                "Текущая версия SG-Gateway продолжает работать нормально."
            )
        return cached

    if not refresh and _CACHE and now - _CACHE[0] < CACHE_TTL_SECONDS:
        return _decorate(_CACHE[1])

    try:
        sha, latest_date, html_url = _latest_channel()
        latest_version = _remote_version(sha)
        result = {
            "checked": True,
            "error": "",
            "repo": GITHUB_REPO,
            "channel": GITHUB_BRANCH,
            "installed_version": installed_version,
            "installed_commit": installed_commit,
            "source_fingerprint": current_fingerprint,
            "baseline_valid": baseline_valid,
            "bootstrap_allowed": False,
            "latest_commit": sha,
            "latest_short": sha[:8],
            "latest_version": latest_version,
            "latest_date": latest_date,
            "html_url": html_url,
            "state": "unavailable",
            "can_install": False,
            "message": "",
        }
        result = _decorate(result)
        _CACHE = (now, result)
        return dict(result)
    except PanelUpdateError as exc:
        return {
            "checked": False,
            "error": str(exc),
            "repo": GITHUB_REPO,
            "channel": GITHUB_BRANCH,
            "installed_version": installed_version,
            "installed_commit": installed_commit,
            "source_fingerprint": current_fingerprint,
            "baseline_valid": baseline_valid,
            "bootstrap_allowed": False,
            "latest_commit": "",
            "latest_short": "",
            "latest_version": "",
            "latest_date": "",
            "html_url": "",
            "state": "unavailable",
            "can_install": False,
            "message": "Проверка GitHub не выполнена.",
        }
