from __future__ import annotations

import fcntl
import hashlib
import json
import os
import re
import shutil
import subprocess
import tarfile
import tempfile
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.maintenance.operations import log_operation
from app.maintenance.panel_updates import GITHUB_API, GITHUB_BRANCH, GITHUB_REPO, STATE_FILE, source_fingerprint


LIVE_ROOT = Path(os.getenv("SG_GATEWAY_APP_ROOT", "/opt/sg-gateway"))
UPDATE_ROOT = Path(os.getenv("SG_GATEWAY_PANEL_UPDATE_DIR", "/var/lib/sg-gateway/updates/panel"))
BACKUP_ROOT = UPDATE_ROOT / "backups"
LOCK_FILE = Path("/run/sg-gateway/panel-update.lock")
ENV_FILE = Path("/etc/sg-gateway/sg-gateway.env")
MAX_ARCHIVE_BYTES = 256 * 1024 * 1024
RESERVE_BYTES = 128 * 1024 * 1024
_SHA_RE = re.compile(r"^[0-9a-f]{40}$")


class PanelUpdateRuntimeError(RuntimeError):
    pass


def _headers() -> dict[str, str]:
    return {
        "Accept": "application/vnd.github+json",
        "User-Agent": "SG-Gateway-Panel-Updater",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def _request_json(url: str, timeout: float = 20.0) -> Any:
    request = urllib.request.Request(url, headers=_headers())
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except (OSError, urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError) as exc:
        raise PanelUpdateRuntimeError(f"GitHub API недоступен: {exc}") from exc




def _baseline_mode() -> tuple[str, dict[str, Any]]:
    try:
        state = json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return "bootstrap", {}
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise PanelUpdateRuntimeError("Panel Update state повреждён") from exc
    if not isinstance(state, dict):
        raise PanelUpdateRuntimeError("Panel Update state повреждён")
    commit = str(state.get("commit") or "").strip().lower()
    recorded = str(state.get("source_fingerprint") or "").strip().lower()
    if not commit and not recorded:
        return "bootstrap", state
    current = source_fingerprint(LIVE_ROOT)
    if not _SHA_RE.fullmatch(commit) or not recorded or not current or recorded != current:
        raise PanelUpdateRuntimeError(
            "Автоматическое обновление сейчас недоступно. Текущая версия SG-Gateway продолжает работать нормально."
        )
    return "bound", state


def _curl_text(url: str, timeout: float = 20.0) -> str:
    try:
        completed = subprocess.run(
            ["curl", "-4", "-fsSL", "--max-time", str(max(1, int(timeout))), "-A", "SG-Gateway-Panel-Updater", url],
            capture_output=True,
            text=True,
            timeout=max(2.0, timeout + 2.0),
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise PanelUpdateRuntimeError(f"GitHub недоступен: {exc}") from exc
    if completed.returncode != 0:
        detail = (completed.stderr or "").strip()
        raise PanelUpdateRuntimeError(f"GitHub недоступен через curl: {detail or f'rc={completed.returncode}'}")
    return completed.stdout


def _latest_channel_commit() -> str:
    try:
        payload = _request_json(f"{GITHUB_API}/commits/{GITHUB_BRANCH}")
        if not isinstance(payload, dict):
            raise PanelUpdateRuntimeError("GitHub не вернул commit update-channel")
        sha = str(payload.get("sha") or "").strip().lower()
        if not _SHA_RE.fullmatch(sha):
            raise PanelUpdateRuntimeError("GitHub вернул некорректный SHA update-channel")
        return sha
    except PanelUpdateRuntimeError:
        try:
            atom = _curl_text(f"https://github.com/{GITHUB_REPO}/commits/{GITHUB_BRANCH}.atom", timeout=20.0)
        except PanelUpdateRuntimeError as exc:
            raise PanelUpdateRuntimeError(f"GitHub {GITHUB_BRANCH} недоступен: {exc}") from exc
        match = re.search(r"Grit::Commit/([0-9a-fA-F]{40})", atom)
        if not match:
            raise PanelUpdateRuntimeError(f"GitHub {GITHUB_BRANCH} не удалось определить ни через API, ни через Atom feed")
        return match.group(1).lower()


def _download_archive(commit: str, destination: Path) -> None:
    url = f"https://github.com/{GITHUB_REPO}/archive/{commit}.tar.gz"
    request = urllib.request.Request(url, headers={"User-Agent": "SG-Gateway-Panel-Updater"})
    try:
        with urllib.request.urlopen(request, timeout=180) as response, destination.open("wb") as stream:
            total = 0
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                if total > MAX_ARCHIVE_BYTES:
                    raise PanelUpdateRuntimeError("Архив GitHub update-channel неожиданно большой")
                stream.write(chunk)
            stream.flush()
            os.fsync(stream.fileno())
    except PanelUpdateRuntimeError:
        destination.unlink(missing_ok=True)
        raise
    except (OSError, urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as exc:
        destination.unlink(missing_ok=True)
        raise PanelUpdateRuntimeError(f"Не удалось скачать snapshot commit {commit[:8]}: {exc}") from exc
    if not destination.is_file() or destination.stat().st_size < 16 * 1024:
        raise PanelUpdateRuntimeError("Скачанный snapshot GitHub выглядит неполным")


def _safe_extract(archive: Path, destination: Path, commit: str) -> Path:
    destination.mkdir(parents=True, exist_ok=True)
    base = destination.resolve()
    try:
        with tarfile.open(archive, "r:gz") as bundle:
            members = bundle.getmembers()
            if not members:
                raise PanelUpdateRuntimeError("Snapshot GitHub пуст")
            roots: set[str] = set()
            for member in members:
                if member.issym() or member.islnk() or member.isdev():
                    raise PanelUpdateRuntimeError(f"Snapshot содержит запрещённый тип файла: {member.name}")
                parts = Path(member.name).parts
                if not parts:
                    continue
                roots.add(parts[0])
                target = (destination / member.name).resolve()
                if target != base and base not in target.parents:
                    raise PanelUpdateRuntimeError(f"Небезопасный путь в snapshot: {member.name}")
            if len(roots) != 1:
                raise PanelUpdateRuntimeError("Snapshot GitHub имеет неожиданную структуру")
            bundle.extractall(destination)
    except (OSError, tarfile.TarError) as exc:
        raise PanelUpdateRuntimeError(f"Не удалось распаковать snapshot: {exc}") from exc
    root = destination / next(iter(roots))
    if not root.is_dir():
        raise PanelUpdateRuntimeError("Не найден корень распакованного snapshot")
    # GitHub archive prefixes the tree with repository name + short/full commit.
    if commit[:7] not in root.name and commit not in root.name:
        raise PanelUpdateRuntimeError("Распакованный snapshot не соответствует запрошенному commit")
    return root


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _version_key(value: str) -> tuple[int, ...]:
    numbers = re.findall(r"\d+", str(value or ""))
    return tuple(int(item) for item in numbers) if numbers else ()


def _validate_snapshot(root: Path) -> tuple[str, str]:
    required = (
        "VERSION",
        "requirements.txt",
        "app/main.py",
        "app/production.py",
        "hostd/sg_hostd/app.py",
        "hostd/sg_hostd/commands.py",
        "app/web/templates/base.html",
    )
    missing = [name for name in required if not (root / name).is_file()]
    if missing:
        raise PanelUpdateRuntimeError("Snapshot неполон: " + ", ".join(missing))
    current_version = (LIVE_ROOT / "VERSION").read_text(encoding="utf-8").strip()
    target_version = (root / "VERSION").read_text(encoding="utf-8").strip()
    if not _version_key(target_version):
        raise PanelUpdateRuntimeError(f"Некорректная VERSION в snapshot: {target_version!r}")
    if _version_key(current_version) and _version_key(target_version) < _version_key(current_version):
        raise PanelUpdateRuntimeError(f"Понижение SG-Gateway {current_version} → {target_version} заблокировано")
    current_req = LIVE_ROOT / "requirements.txt"
    target_req = root / "requirements.txt"
    if not current_req.is_file():
        raise PanelUpdateRuntimeError("В текущей установке отсутствует requirements.txt")
    if _sha256(current_req) != _sha256(target_req):
        raise PanelUpdateRuntimeError(
            "requirements.txt изменён. Безопасный panel-only update заблокирован; нужен новый полный installer с проверкой зависимостей."
        )
    python = LIVE_ROOT / ".venv/bin/python"
    if not python.is_file():
        raise PanelUpdateRuntimeError("Не найдено рабочее Python-окружение /opt/sg-gateway/.venv")
    result = subprocess.run(
        [str(python), "-m", "compileall", "-q", str(root / "app"), str(root / "hostd")],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    if result.returncode:
        raise PanelUpdateRuntimeError((result.stderr or result.stdout or "py_compile failed").strip())
    # Import against the staged source while keeping the proven existing venv.
    env = dict(os.environ)
    env["PYTHONPATH"] = f"{root}:{root / 'hostd'}"
    env["SG_GATEWAY_ENV"] = "production"
    validation_root = root.parent / "wsgi-validation"
    (validation_root / "data").mkdir(parents=True, exist_ok=True)
    (validation_root / "log").mkdir(parents=True, exist_ok=True)
    env["SG_GATEWAY_DATA_DIR"] = str(validation_root / "data")
    env["SG_GATEWAY_LOG_DIR"] = str(validation_root / "log")
    check = subprocess.run(
        [str(python), "-c", "import app.production; import sg_hostd.commands; print('imports-ok')"],
        cwd=str(root),
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    if check.returncode:
        raise PanelUpdateRuntimeError((check.stderr or check.stdout or "staged imports failed").strip())
    return current_version, target_version


def _source_size(root: Path) -> int:
    total = 0
    for path in root.rglob("*"):
        if path.is_file() and ".venv" not in path.parts and "__pycache__" not in path.parts:
            try:
                total += path.stat().st_size
            except OSError:
                pass
    return total


def _check_space(snapshot_root: Path) -> None:
    size = max(_source_size(LIVE_ROOT), _source_size(snapshot_root))
    free = shutil.disk_usage(UPDATE_ROOT.parent if UPDATE_ROOT.parent.exists() else Path("/var/lib/sg-gateway")).free
    required = size * 3 + RESERVE_BYTES
    if free < required:
        raise PanelUpdateRuntimeError(
            f"Недостаточно свободного места для snapshot+backup: требуется около {required // (1024*1024)} MiB, доступно {free // (1024*1024)} MiB"
        )


def _ignore_source(path: Path) -> bool:
    parts = path.parts
    return (
        ".venv" in parts
        or ".git" in parts
        or "__pycache__" in parts
        or path.suffix in {".pyc", ".pyo"}
        or ("vendor" in parts and "cores" in parts)
    )


def _copy_tree(source: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    for path in source.rglob("*"):
        relative = path.relative_to(source)
        if _ignore_source(relative):
            continue
        target = destination / relative
        if path.is_dir():
            target.mkdir(parents=True, exist_ok=True)
        elif path.is_file():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)


def _backup_live() -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-%f")
    backup = BACKUP_ROOT / stamp
    backup.mkdir(parents=True, exist_ok=False)
    _copy_tree(LIVE_ROOT, backup)
    # Verify a few immutable anchors immediately; a failed backup must stop before mutation.
    for relative in (Path("VERSION"), Path("app/main.py"), Path("hostd/sg_hostd/commands.py")):
        source = LIVE_ROOT / relative
        target = backup / relative
        if not target.is_file() or _sha256(source) != _sha256(target):
            raise PanelUpdateRuntimeError(f"Страховочная копия не прошла проверку: {relative}")
    return backup


def _purge_live_source() -> None:
    for child in LIVE_ROOT.iterdir():
        if child.name == ".venv":
            continue
        if child.is_dir() and not child.is_symlink():
            shutil.rmtree(child)
        else:
            child.unlink(missing_ok=True)


def _deploy_source(source: Path) -> None:
    _purge_live_source()
    _copy_tree(source, LIVE_ROOT)
    for path in LIVE_ROOT.rglob("*"):
        if ".venv" in path.parts:
            continue
        try:
            if path.is_dir():
                os.chmod(path, 0o755)
            elif path.is_file():
                mode = path.stat().st_mode & 0o777
                os.chmod(path, 0o755 if mode & 0o111 else 0o644)
            os.chown(path, 0, 0)
        except OSError as exc:
            raise PanelUpdateRuntimeError(f"Не удалось установить права {path}: {exc}") from exc
    os.chown(LIVE_ROOT, 0, 0)
    os.chmod(LIVE_ROOT, 0o755)


def _service(command: str, service: str, timeout: int = 60) -> None:
    result = subprocess.run(["systemctl", command, service], capture_output=True, text=True, timeout=timeout, check=False)
    if result.returncode:
        raise PanelUpdateRuntimeError((result.stderr or result.stdout or f"systemctl {command} {service} failed").strip())


def _env_port(name: str, default: int) -> int:
    try:
        for raw in ENV_FILE.read_text(encoding="utf-8", errors="replace").splitlines():
            if raw.startswith(name + "="):
                return int(raw.split("=", 1)[1].strip().strip('"\''))
    except (OSError, ValueError):
        pass
    return default


def _wait_health(url: str, label: str, timeout: float = 30.0) -> None:
    deadline = time.monotonic() + timeout
    last = ""
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2.0) as response:
                if 200 <= response.status < 300:
                    return
                last = f"HTTP {response.status}"
        except Exception as exc:  # health retry loop intentionally collects transient startup errors
            last = str(exc)
        time.sleep(0.5)
    raise PanelUpdateRuntimeError(f"{label} не прошёл health-check: {last or 'timeout'}")


def _start_and_verify() -> None:
    _service("daemon-reload", "", timeout=30) if False else None
    _service("start", "sg-hostd.service")
    _service("is-active", "sg-hostd.service", timeout=20)
    _wait_health(f"http://127.0.0.1:{_env_port('SG_GATEWAY_HOSTD_PORT', 8090)}/health", "sg-hostd")
    _service("start", "sg-gateway.service")
    _service("is-active", "sg-gateway.service", timeout=20)
    _wait_health(f"http://127.0.0.1:{_env_port('SG_GATEWAY_PORT', 18080)}/health", "sg-gateway")


def _write_state(commit: str, version: str, backup: Path) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "commit": commit,
        "version": version,
        "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "backup": backup.name,
        "source_fingerprint": source_fingerprint(LIVE_ROOT),
    }
    temporary = STATE_FILE.with_suffix(".json.new")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.chmod(temporary, 0o640)
    os.replace(temporary, STATE_FILE)


def update_panel() -> dict[str, Any]:
    """Compatibility entrypoint: delegate to the verified full-state shell updater."""
    script = LIVE_ROOT / "deploy" / "update-from-github.sh"
    if not script.is_file():
        raise PanelUpdateRuntimeError(f"Не найден безопасный updater: {script}")
    env = dict(os.environ)
    env["SG_GATEWAY_GITHUB_BRANCH"] = GITHUB_BRANCH
    completed = subprocess.run(
        ["/bin/bash", str(script)],
        cwd=str(LIVE_ROOT),
        env=env,
        capture_output=True,
        text=True,
        timeout=1800,
        check=False,
    )
    output = "\n".join(
        part.strip() for part in (completed.stdout, completed.stderr) if part and part.strip()
    )
    if output:
        print(output, flush=True)
    if completed.returncode:
        raise PanelUpdateRuntimeError(
            output.splitlines()[-1] if output else f"safe updater failed: rc={completed.returncode}"
        )
    version = (LIVE_ROOT / "VERSION").read_text(encoding="utf-8").strip()
    return {
        "ok": True,
        "message": f"SG-Gateway безопасно обновлён из GitHub {GITHUB_BRANCH}; VERSION {version}",
        "channel": GITHUB_BRANCH,
        "version": version,
    }
