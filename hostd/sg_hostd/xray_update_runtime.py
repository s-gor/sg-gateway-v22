from __future__ import annotations

import fcntl
import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import tempfile
import urllib.error
import urllib.request
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.maintenance.operations import log_operation
from app.maintenance.xray_updates import compare_versions, version_key
from app.xray.profiles import XRAY_MINIMUM_VERSION


GITHUB_API = "https://api.github.com/repos/XTLS/Xray-core"
XRAY_BINARY = Path("/usr/local/bin/xray")
XRAY_CONFIG = Path("/usr/local/etc/xray/config.json")
UPDATE_ROOT = Path(os.getenv("SG_GATEWAY_XRAY_UPDATE_DIR", "/var/lib/sg-gateway/xray-updates"))
BACKUP_DIR = UPDATE_ROOT / "backups"
LOCK_FILE = Path("/run/sg-gateway/xray-update.lock")
LAST_RESULT = UPDATE_ROOT / "last-update.json"
_SHA256_RE = re.compile(r"\b([0-9a-fA-F]{64})\b")


class XrayUpdateRuntimeError(RuntimeError):
    pass


def _headers() -> dict[str, str]:
    return {
        "Accept": "application/vnd.github+json",
        "User-Agent": "SG-Gateway-Xray-Updater",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def _request_json(url: str, timeout: float = 20.0) -> Any:
    request = urllib.request.Request(url, headers=_headers())
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except (OSError, urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError) as exc:
        raise XrayUpdateRuntimeError(f"GitHub API недоступен: {exc}") from exc


def _download(url: str, destination: Path, timeout: float = 120.0) -> None:
    request = urllib.request.Request(url, headers={**_headers(), "Accept": "application/octet-stream"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response, destination.open("wb") as stream:
            shutil.copyfileobj(response, stream, length=1024 * 1024)
    except (OSError, urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as exc:
        raise XrayUpdateRuntimeError(f"Не удалось скачать {destination.name}: {exc}") from exc
    if not destination.is_file() or destination.stat().st_size < 1024 * 1024:
        raise XrayUpdateRuntimeError(f"Скачанный архив {destination.name} выглядит неполным")


def _run(command: list[str], *, timeout: int = 90) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(command, capture_output=True, text=True, timeout=timeout, check=False)
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        raise XrayUpdateRuntimeError(detail or f"Команда завершилась с кодом {result.returncode}: {' '.join(command)}")
    return result


def _installed_version(binary: Path = XRAY_BINARY) -> str:
    if not binary.is_file():
        return ""
    result = _run([str(binary), "version"], timeout=15)
    lines = (result.stdout or result.stderr or "").splitlines()
    if not lines:
        raise XrayUpdateRuntimeError("Xray не вернул версию")
    parts = lines[0].split()
    if len(parts) < 2 or not version_key(parts[1]):
        raise XrayUpdateRuntimeError(f"Не удалось разобрать версию Xray: {lines[0]}")
    return parts[1].lstrip("v")


def _latest_release(channel: str) -> dict[str, Any]:
    if channel == "stable":
        payload = _request_json(f"{GITHUB_API}/releases/latest")
        if not isinstance(payload, dict) or payload.get("draft") or payload.get("prerelease"):
            raise XrayUpdateRuntimeError("GitHub не вернул стабильный релиз Xray")
        return payload
    if channel != "prerelease":
        raise XrayUpdateRuntimeError(f"Неизвестный канал Xray: {channel}")
    payload = _request_json(f"{GITHUB_API}/releases?per_page=30")
    if not isinstance(payload, list):
        raise XrayUpdateRuntimeError("GitHub не вернул список предварительных релизов Xray")
    candidates = [
        item
        for item in payload
        if isinstance(item, dict)
        and item.get("prerelease")
        and not item.get("draft")
        and version_key(str(item.get("tag_name") or ""))
    ]
    if not candidates:
        raise XrayUpdateRuntimeError("Предварительные релизы Xray не найдены")
    return max(candidates, key=lambda item: version_key(str(item.get("tag_name") or "")))


def _asset_filename() -> str:
    machine = platform.machine().lower()
    mapping = {
        "x86_64": "Xray-linux-64.zip",
        "amd64": "Xray-linux-64.zip",
        "aarch64": "Xray-linux-arm64-v8a.zip",
        "arm64": "Xray-linux-arm64-v8a.zip",
        "armv7l": "Xray-linux-arm32-v7a.zip",
        "armv7": "Xray-linux-arm32-v7a.zip",
    }
    try:
        return mapping[machine]
    except KeyError as exc:
        raise XrayUpdateRuntimeError(f"Архитектура {machine or 'unknown'} пока не поддерживается") from exc


def _find_asset(release: dict[str, Any], name: str) -> dict[str, Any]:
    assets = release.get("assets")
    if not isinstance(assets, list):
        raise XrayUpdateRuntimeError("В релизе Xray нет списка файлов")
    for asset in assets:
        if isinstance(asset, dict) and asset.get("name") == name:
            return asset
    raise XrayUpdateRuntimeError(f"В релизе не найден файл {name}")


def _expected_digest(release: dict[str, Any], asset: dict[str, Any], workdir: Path) -> str:
    digest = str(asset.get("digest") or "").strip().lower()
    if digest.startswith("sha256:") and _SHA256_RE.fullmatch(digest.split(":", 1)[1]):
        return digest.split(":", 1)[1]

    digest_asset = _find_asset(release, f"{asset.get('name')}.dgst")
    digest_url = str(digest_asset.get("browser_download_url") or "")
    if not digest_url:
        raise XrayUpdateRuntimeError("У файла проверки SHA-256 отсутствует URL")
    digest_path = workdir / str(digest_asset.get("name") or "xray.dgst")
    _download_small(digest_url, digest_path)
    matches = _SHA256_RE.findall(digest_path.read_text(encoding="utf-8", errors="replace"))
    if not matches:
        raise XrayUpdateRuntimeError("Не удалось прочитать SHA-256 из официального .dgst")
    return matches[0].lower()


def _download_small(url: str, destination: Path, timeout: float = 30.0) -> None:
    request = urllib.request.Request(url, headers={**_headers(), "Accept": "application/octet-stream"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read(1024 * 1024)
    except (OSError, urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as exc:
        raise XrayUpdateRuntimeError(f"Не удалось скачать контрольную сумму: {exc}") from exc
    destination.write_bytes(body)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _extract_binary(archive: Path, destination: Path) -> None:
    try:
        with zipfile.ZipFile(archive) as bundle:
            names = [name for name in bundle.namelist() if Path(name).name == "xray"]
            if len(names) != 1:
                raise XrayUpdateRuntimeError("В архиве Xray не найден единственный бинарник xray")
            with bundle.open(names[0]) as source, destination.open("wb") as target:
                shutil.copyfileobj(source, target)
    except (OSError, zipfile.BadZipFile) as exc:
        raise XrayUpdateRuntimeError(f"Не удалось распаковать Xray: {exc}") from exc
    os.chmod(destination, 0o755)


def _test_config(binary: Path) -> None:
    if not XRAY_CONFIG.is_file():
        raise XrayUpdateRuntimeError(f"Не найден рабочий config.json: {XRAY_CONFIG}")
    _run([str(binary), "run", "-test", "-config", str(XRAY_CONFIG)], timeout=120)


def _write_result(payload: dict[str, Any]) -> None:
    UPDATE_ROOT.mkdir(parents=True, exist_ok=True)
    temporary = LAST_RESULT.with_suffix(".json.new")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.chmod(temporary, 0o640)
    os.replace(temporary, LAST_RESULT)


def _restore_binary(backup: Path) -> None:
    rollback = XRAY_BINARY.with_name("xray.rollback")
    shutil.copy2(backup, rollback)
    os.chmod(rollback, 0o755)
    os.replace(rollback, XRAY_BINARY)
    _run(["systemctl", "restart", "xray.service"], timeout=60)
    _run(["systemctl", "is-active", "--quiet", "xray.service"], timeout=30)
    _test_config(XRAY_BINARY)


def update_xray(channel: str) -> dict[str, Any]:
    LOCK_FILE.parent.mkdir(parents=True, exist_ok=True)
    with LOCK_FILE.open("w", encoding="utf-8") as lock:
        try:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise XrayUpdateRuntimeError("Другая операция обновления Xray уже выполняется") from exc

        installed = _installed_version()
        if not installed:
            raise XrayUpdateRuntimeError("Установленный Xray не найден")
        recovery_upgrade = compare_versions(installed, XRAY_MINIMUM_VERSION) < 0

        release = _latest_release(channel)
        tag = str(release.get("tag_name") or "").strip()
        target = tag.lstrip("v")
        if not version_key(target):
            raise XrayUpdateRuntimeError(f"Некорректная версия релиза: {tag or 'пусто'}")
        if compare_versions(target, XRAY_MINIMUM_VERSION) < 0:
            raise XrayUpdateRuntimeError(
                f"целевая версия Xray v{target} ниже минимально поддерживаемой v{XRAY_MINIMUM_VERSION}"
            )
        comparison = compare_versions(target, installed)
        if comparison == 0:
            raise XrayUpdateRuntimeError(f"Xray v{target} уже установлен")
        if comparison < 0:
            raise XrayUpdateRuntimeError(
                f"Понижение Xray с v{installed} до v{target} заблокировано"
            )
        if recovery_upgrade:
            print(
                f"[Xray Update] Восстановительное обновление: установлен v{installed}, "
                f"минимум v{XRAY_MINIMUM_VERSION}; продолжаю до v{target}",
                flush=True,
            )

        asset_name = _asset_filename()
        asset = _find_asset(release, asset_name)
        download_url = str(asset.get("browser_download_url") or "")
        if not download_url:
            raise XrayUpdateRuntimeError(f"У {asset_name} отсутствует URL загрузки")

        UPDATE_ROOT.mkdir(parents=True, exist_ok=True)
        BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        os.chmod(UPDATE_ROOT, 0o750)
        os.chmod(BACKUP_DIR, 0o750)
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        backup = BACKUP_DIR / f"xray-v{installed}-{timestamp}"
        result_payload: dict[str, Any] = {
            "ok": False,
            "channel": channel,
            "from_version": installed,
            "to_version": target,
            "asset": asset_name,
            "backup": str(backup),
            "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }

        with tempfile.TemporaryDirectory(prefix="candidate-", dir=UPDATE_ROOT) as temp_name:
            workdir = Path(temp_name)
            archive = workdir / asset_name
            candidate = workdir / "xray"
            print(f"[Xray Update 1/7] Канал: {channel}; установлена v{installed}; цель v{target}", flush=True)
            print(f"[Xray Update 2/7] Скачиваю официальный {asset_name}", flush=True)
            _download(download_url, archive)
            expected = _expected_digest(release, asset, workdir)
            actual = _sha256(archive)
            if actual != expected:
                raise XrayUpdateRuntimeError(
                    f"SHA-256 не совпадает: ожидался {expected}, получен {actual}"
                )
            print(f"[Xray Update 3/7] SHA-256 подтверждён: {actual}", flush=True)
            _extract_binary(archive, candidate)
            candidate_version = _installed_version(candidate)
            if candidate_version != target:
                raise XrayUpdateRuntimeError(
                    f"Архив содержит Xray v{candidate_version or 'unknown'}, ожидалась v{target}"
                )
            print("[Xray Update 4/7] Проверяю текущий config.json новым бинарником", flush=True)
            _test_config(candidate)

            shutil.copy2(XRAY_BINARY, backup)
            os.chmod(backup, 0o750)
            staged = XRAY_BINARY.with_name("xray.sg-gateway-new")
            shutil.copy2(candidate, staged)
            os.chmod(staged, 0o755)
            print(f"[Xray Update 5/7] Создана страховочная копия {backup}", flush=True)
            replaced = False
            try:
                os.replace(staged, XRAY_BINARY)
                replaced = True
                print("[Xray Update 6/7] Перезапускаю xray.service", flush=True)
                _run(["systemctl", "restart", "xray.service"], timeout=60)
                _run(["systemctl", "is-active", "--quiet", "xray.service"], timeout=30)
                running = _installed_version()
                if running != target:
                    raise XrayUpdateRuntimeError(
                        f"После перезапуска обнаружена v{running or 'unknown'}, ожидалась v{target}"
                    )
                _test_config(XRAY_BINARY)
            except Exception as exc:
                print(f"[Xray Update] Ошибка после замены: {exc}", flush=True)
                if replaced and backup.is_file():
                    print(f"[Xray Update] Автоматически возвращаю Xray v{installed}", flush=True)
                    try:
                        _restore_binary(backup)
                        print("[Xray Update] Откат завершён, прежняя версия снова работает", flush=True)
                    except Exception as rollback_exc:
                        raise XrayUpdateRuntimeError(
                            f"Обновление не удалось: {exc}; автоматический откат также не удался: {rollback_exc}"
                        ) from rollback_exc
                raise XrayUpdateRuntimeError(f"Обновление отменено, прежняя версия восстановлена: {exc}") from exc
            finally:
                staged.unlink(missing_ok=True)

        result_payload.update({"ok": True, "message": f"Xray обновлён с v{installed} до v{target}"})
        try:
            _write_result(result_payload)
        except OSError as exc:
            print(f"[Xray Update] Предупреждение: не удалось сохранить итог операции: {exc}", flush=True)
        try:
            log_operation("xray.update", channel, result_payload["message"], "ok")
        except Exception as exc:
            print(f"[Xray Update] Предупреждение: журнал панели не обновлён: {exc}", flush=True)
        print(f"[Xray Update 7/7] {result_payload['message']}", flush=True)
        return result_payload
