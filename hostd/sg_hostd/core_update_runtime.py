from __future__ import annotations

import fcntl
import gzip
import hashlib
import json
import os
import platform
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

from app.maintenance.core_updates import SPECS, CoreSpec
from app.maintenance.operations import log_operation
from app.maintenance.xray_updates import compare_versions, version_key


UPDATE_ROOT = Path(os.getenv("SG_GATEWAY_CORE_UPDATE_DIR", "/var/lib/sg-gateway/updates/cores"))
BACKUP_ROOT = UPDATE_ROOT / "backups"
LOCK_FILE = Path("/run/sg-gateway/core-update.lock")
INSTALL_ENV = Path(os.getenv("SG_GATEWAY_INSTALL_ENV", "/etc/sg-gateway/runtime.env"))
_SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")
_VERSION_RE = re.compile(r"(?:^|\s)v?(\d+(?:\.\d+){1,3})(?:\s|$)")
_ANSI_ESCAPE_RE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")


class CoreUpdateRuntimeError(RuntimeError):
    pass


def _headers() -> dict[str, str]:
    return {
        "Accept": "application/vnd.github+json",
        "User-Agent": "SG-Gateway-Core-Updater",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def _request_json(url: str, timeout: float = 20.0) -> Any:
    request = urllib.request.Request(url, headers=_headers())
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except (OSError, urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError) as exc:
        raise CoreUpdateRuntimeError(f"GitHub API недоступен: {exc}") from exc


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _parse_version(text: str) -> str:
    clean = _ANSI_ESCAPE_RE.sub("", str(text or ""))
    for line in clean.splitlines():
        match = _VERSION_RE.search(line.strip())
        if match and version_key(match.group(1)):
            return match.group(1)
    return ""


def _run(command: list[str], *, timeout: int = 60) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(command, capture_output=True, text=True, timeout=timeout, check=False)
    if result.returncode:
        raise CoreUpdateRuntimeError((result.stderr or result.stdout or f"Команда завершилась с кодом {result.returncode}").strip())
    return result


def _spec(engine: str) -> CoreSpec:
    for item in SPECS:
        if item.engine == engine:
            return item
    raise CoreUpdateRuntimeError(f"Неподдерживаемое ядро: {engine}")


def _version_commands(spec: CoreSpec, path: Path) -> list[list[str]]:
    executable = str(path)
    if spec.engine == "mihomo":
        return [[executable, "-v"], [executable, "--version"]]
    if spec.engine == "sing-box":
        return [[executable, "version"], [executable, "--version"]]
    if spec.engine == "wgcf":
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


def _installed_version(
    spec: CoreSpec,
    binary: Path | None = None,
    *,
    allow_env_fallback: bool = True,
) -> str:
    path = binary or Path(spec.binary)
    if not path.is_file():
        return ""
    diagnostics: list[str] = []
    for command in _version_commands(spec, path):
        try:
            result = subprocess.run(command, capture_output=True, text=True, timeout=15, check=False)
        except (OSError, subprocess.SubprocessError) as exc:
            diagnostics.append(f"{' '.join(command[1:])}: {exc}")
            continue
        output = (result.stdout or "") + "\n" + (result.stderr or "")
        value = _parse_version(output)
        if value:
            return value
        diagnostics.append(f"{' '.join(command[1:])}: rc={result.returncode}, output={output.strip()[:160]!r}")
    if allow_env_fallback and binary is None:
        recorded = _install_env_version(spec)
        if recorded:
            print(
                f"[Core Update] {spec.title}: binary version probe не распознан; "
                f"использую версию установщика v{recorded}",
                flush=True,
            )
            return recorded
    detail = "; ".join(diagnostics) or "нет доступных version-команд"
    raise CoreUpdateRuntimeError(f"Не удалось определить версию {spec.title}: {detail}")


def _release(spec: CoreSpec) -> dict[str, Any]:
    payload = _request_json(f"https://api.github.com/repos/{spec.repo}/releases/latest")
    if not isinstance(payload, dict) or payload.get("draft") or payload.get("prerelease"):
        raise CoreUpdateRuntimeError(f"GitHub не вернул стабильный релиз {spec.title}")
    tag = str(payload.get("tag_name") or "").strip()
    target = tag.lstrip("v")
    if not version_key(target):
        raise CoreUpdateRuntimeError(f"Некорректная версия {spec.title}: {tag or 'пусто'}")
    return payload


def _asset_name(spec: CoreSpec, version: str) -> str:
    machine = platform.machine().lower()
    if machine not in {"x86_64", "amd64"}:
        raise CoreUpdateRuntimeError(f"Core Update 021 поддерживает только linux/amd64; найдено {machine or 'unknown'}")
    if spec.engine == "mihomo":
        return f"mihomo-linux-amd64-v{version}.gz"
    if spec.engine == "sing-box":
        return f"sing-box-{version}-linux-amd64.tar.gz"
    if spec.engine == "wgcf":
        return "wgcf-cli-linux-64.tar.zstd"
    raise CoreUpdateRuntimeError(f"Неизвестный asset для {spec.engine}")


def _find_asset(release: dict[str, Any], name: str) -> dict[str, Any]:
    assets = release.get("assets")
    if not isinstance(assets, list):
        raise CoreUpdateRuntimeError("GitHub Release не содержит assets")
    for asset in assets:
        if isinstance(asset, dict) and str(asset.get("name") or "") == name:
            return asset
    raise CoreUpdateRuntimeError(f"В GitHub Release не найден {name}")


def _expected_sha(asset: dict[str, Any]) -> str:
    digest = str(asset.get("digest") or "").strip().lower()
    if digest.startswith("sha256:"):
        value = digest.split(":", 1)[1]
        if _SHA256_RE.fullmatch(value):
            return value
    raise CoreUpdateRuntimeError(
        "GitHub Release не предоставил официальный SHA-256 для этого asset. Обновление заблокировано."
    )


def _download(url: str, destination: Path, *, max_bytes: int = 192 * 1024 * 1024) -> None:
    request = urllib.request.Request(url, headers={**_headers(), "Accept": "application/octet-stream"})
    total = 0
    try:
        with urllib.request.urlopen(request, timeout=180) as response, destination.open("wb") as stream:
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                if total > max_bytes:
                    raise CoreUpdateRuntimeError("Скачиваемый asset неожиданно большой")
                stream.write(chunk)
            stream.flush()
            os.fsync(stream.fileno())
    except CoreUpdateRuntimeError:
        destination.unlink(missing_ok=True)
        raise
    except (OSError, urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as exc:
        destination.unlink(missing_ok=True)
        raise CoreUpdateRuntimeError(f"Не удалось скачать {destination.name}: {exc}") from exc
    if total < 128 * 1024:
        raise CoreUpdateRuntimeError(f"Скачанный {destination.name} выглядит неполным")


def _extract(spec: CoreSpec, archive: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if spec.engine == "mihomo":
        try:
            with gzip.open(archive, "rb") as source, destination.open("wb") as target:
                shutil.copyfileobj(source, target, length=1024 * 1024)
        except (OSError, EOFError) as exc:
            raise CoreUpdateRuntimeError(f"Не удалось распаковать Mihomo: {exc}") from exc
    elif spec.engine == "sing-box":
        try:
            with tarfile.open(archive, "r:gz") as bundle:
                members = [member for member in bundle.getmembers() if member.isfile() and Path(member.name).name == "sing-box"]
                if len(members) != 1:
                    raise CoreUpdateRuntimeError("В sing-box archive не найден единственный бинарник")
                source = bundle.extractfile(members[0])
                if source is None:
                    raise CoreUpdateRuntimeError("Не удалось открыть sing-box binary")
                with source, destination.open("wb") as target:
                    shutil.copyfileobj(source, target, length=1024 * 1024)
        except (OSError, tarfile.TarError) as exc:
            raise CoreUpdateRuntimeError(f"Не удалось распаковать sing-box: {exc}") from exc
    elif spec.engine == "wgcf":
        temp_tar = destination.with_suffix(".tar")
        _run(["zstd", "-q", "-d", "-f", str(archive), "-o", str(temp_tar)], timeout=90)
        try:
            with tarfile.open(temp_tar, "r:") as bundle:
                members = [member for member in bundle.getmembers() if member.isfile() and Path(member.name).name == "wgcf-cli"]
                if len(members) != 1:
                    raise CoreUpdateRuntimeError("В wgcf archive не найден единственный wgcf-cli")
                source = bundle.extractfile(members[0])
                if source is None:
                    raise CoreUpdateRuntimeError("Не удалось открыть wgcf-cli binary")
                with source, destination.open("wb") as target:
                    shutil.copyfileobj(source, target, length=1024 * 1024)
        finally:
            temp_tar.unlink(missing_ok=True)
    else:
        raise CoreUpdateRuntimeError(f"Распаковка {spec.engine} не поддерживается")
    os.chmod(destination, 0o755)


def _test_candidate(spec: CoreSpec, candidate: Path, target_version: str) -> None:
    actual = _installed_version(spec, candidate, allow_env_fallback=False)
    if compare_versions(actual, target_version) != 0:
        raise CoreUpdateRuntimeError(f"Кандидат {spec.title} вернул v{actual}, ожидалась v{target_version}")
    if spec.engine == "mihomo" and Path("/etc/mihomo/config.yaml").is_file():
        _run([str(candidate), "-t", "-d", "/var/lib/mihomo", "-f", "/etc/mihomo/config.yaml"], timeout=60)
    if spec.engine == "sing-box" and Path("/etc/sing-box/config.json").is_file():
        _run([str(candidate), "check", "-c", "/etc/sing-box/config.json"], timeout=60)


def _service_for(spec: CoreSpec) -> str:
    return {"mihomo": "mihomo.service", "sing-box": "sg-gateway-singbox.service", "wgcf": ""}[spec.engine]


def _is_active(service: str) -> bool:
    if not service:
        return False
    return subprocess.run(["systemctl", "is-active", "--quiet", service], timeout=20, check=False).returncode == 0


def _restore(binary: Path, backup: Path, service: str, was_active: bool) -> None:
    temporary = binary.with_name(binary.name + ".rollback")
    shutil.copy2(backup, temporary)
    os.chmod(temporary, 0o755)
    os.replace(temporary, binary)
    if was_active and service:
        _run(["systemctl", "restart", service], timeout=90)
        _run(["systemctl", "is-active", "--quiet", service], timeout=30)


def update_core(engine: str) -> dict[str, Any]:
    spec = _spec(engine)
    LOCK_FILE.parent.mkdir(parents=True, exist_ok=True)
    with LOCK_FILE.open("w", encoding="utf-8") as lock:
        try:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise CoreUpdateRuntimeError("Другая операция Core Update уже выполняется") from exc

        binary = Path(spec.binary)
        installed = _installed_version(spec)
        if not installed:
            raise CoreUpdateRuntimeError(f"{spec.title} не установлен")
        release = _release(spec)
        tag = str(release.get("tag_name") or "")
        target = tag.lstrip("v")
        comparison = compare_versions(target, installed)
        if comparison == 0:
            raise CoreUpdateRuntimeError(f"{spec.title} v{target} уже установлен")
        if comparison < 0:
            raise CoreUpdateRuntimeError(f"Понижение {spec.title} v{installed} → v{target} заблокировано")

        asset_name = _asset_name(spec, target)
        asset = _find_asset(release, asset_name)
        expected = _expected_sha(asset)
        url = str(asset.get("browser_download_url") or "")
        if not url.startswith("https://"):
            raise CoreUpdateRuntimeError("GitHub asset не содержит безопасный HTTPS URL")

        UPDATE_ROOT.mkdir(parents=True, exist_ok=True)
        backup_dir = BACKUP_ROOT / spec.engine
        backup_dir.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix=f"sg-core-{spec.engine}-", dir=str(UPDATE_ROOT)) as temp_name:
            temp = Path(temp_name)
            archive = temp / asset_name
            candidate = temp / binary.name
            print(f"[Core Update 1/7] {spec.title}: v{installed} → v{target}", flush=True)
            _download(url, archive)
            actual = _sha256(archive)
            if actual.lower() != expected.lower():
                raise CoreUpdateRuntimeError(f"SHA-256 {asset_name} не совпал: {actual} != {expected}")
            print(f"[Core Update 2/7] Официальный SHA-256 подтверждён: {actual}", flush=True)
            _extract(spec, archive, candidate)
            _test_candidate(spec, candidate, target)
            print("[Core Update 3/7] Новый binary и текущая конфигурация прошли предварительную проверку", flush=True)

            stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-%f")
            backup = backup_dir / f"{binary.name}-{installed}-{stamp}"
            shutil.copy2(binary, backup)
            os.chmod(backup, 0o755)
            if _sha256(backup) != _sha256(binary):
                raise CoreUpdateRuntimeError("Backup текущего binary не прошёл SHA-проверку")
            print(f"[Core Update 4/7] Backup создан и проверен: {backup.name}", flush=True)

            service = _service_for(spec)
            was_active = _is_active(service)
            try:
                replacement = binary.with_name(binary.name + ".new")
                shutil.copy2(candidate, replacement)
                os.chmod(replacement, 0o755)
                os.replace(replacement, binary)
                print("[Core Update 5/7] Binary заменён атомарно", flush=True)
                if service and was_active:
                    _run(["systemctl", "restart", service], timeout=90)
                    _run(["systemctl", "is-active", "--quiet", service], timeout=30)
                running_version = _installed_version(spec, allow_env_fallback=False)
                if compare_versions(running_version, target) != 0:
                    raise CoreUpdateRuntimeError(f"После замены обнаружена v{running_version}, ожидалась v{target}")
                print("[Core Update 6/7] Runtime проверен", flush=True)
            except Exception as exc:
                _restore(binary, backup, service, was_active)
                raise CoreUpdateRuntimeError(f"Обновление отменено, {spec.title} v{installed} восстановлен: {exc}") from exc

            message = f"{spec.title} обновлён v{installed} → v{target}; backup: {backup.name}"
            try:
                log_operation("core.update", spec.engine, message, "ok")
            except Exception:
                pass
            print(f"[Core Update 7/7] {message}", flush=True)
            return {"ok": True, "engine": spec.engine, "from": installed, "to": target, "backup": backup.name, "message": message}
