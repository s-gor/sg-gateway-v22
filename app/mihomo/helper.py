from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from app.mihomo.service import (
    MIHOMO_APPLIED_META,
    MIHOMO_BACKUP_DIR,
    MIHOMO_BINARY,
    MIHOMO_CANDIDATE,
    MIHOMO_CANDIDATE_META,
    MIHOMO_CONFIG,
    MIHOMO_CONFIG_DIR,
    MIHOMO_STATE_DIR,
    MIHOMO_TLS_DIR,
    MihomoError,
)



def _result(ok: bool, message: str, **extra) -> dict:
    return {"ok": ok, "message": message, **extra}


def _require_root() -> None:
    if os.geteuid() != 0:
        raise MihomoError(
            "Mihomo runtime может изменять /etc/mihomo только через root-службу sg-hostd"
        )


def _run(command: list[str], timeout: int = 120) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    if result.returncode != 0:
        raise MihomoError(
            (result.stderr or result.stdout).strip()
            or f"Команда завершилась с кодом {result.returncode}"
        )
    return result


def _prepare_runtime_dirs() -> None:
    MIHOMO_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    os.chown(MIHOMO_CONFIG_DIR, 0, 0)
    os.chmod(MIHOMO_CONFIG_DIR, 0o711)

    MIHOMO_TLS_DIR.mkdir(parents=True, exist_ok=True)
    os.chown(MIHOMO_TLS_DIR, 0, 0)
    os.chmod(MIHOMO_TLS_DIR, 0o700)

    MIHOMO_STATE_DIR.mkdir(parents=True, exist_ok=True)
    os.chown(MIHOMO_STATE_DIR, 0, 0)
    os.chmod(MIHOMO_STATE_DIR, 0o750)

    MIHOMO_BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    os.chown(MIHOMO_BACKUP_DIR, 0, 0)
    os.chmod(MIHOMO_BACKUP_DIR, 0o700)


def _meta() -> dict:
    try:
        return json.loads(MIHOMO_CANDIDATE_META.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise MihomoError(f"Candidate metadata повреждён: {exc}") from exc


def _copy_atomic(
    source: Path,
    destination: Path,
    mode: int,
) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(destination.name + ".new")
    shutil.copyfile(source, temporary)
    os.chown(temporary, 0, 0)
    os.chmod(temporary, mode)
    os.replace(temporary, destination)


def _backup_current() -> Path:
    _prepare_runtime_dirs()
    backup = MIHOMO_BACKUP_DIR / datetime.now(timezone.utc).strftime(
        "%Y%m%d-%H%M%S-%f"
    )
    backup.mkdir(parents=True, exist_ok=False)
    os.chown(backup, 0, 0)
    os.chmod(backup, 0o700)

    if MIHOMO_CONFIG.is_file():
        _copy_atomic(MIHOMO_CONFIG, backup / "config.yaml", 0o600)
    if MIHOMO_APPLIED_META.is_file():
        _copy_atomic(MIHOMO_APPLIED_META, backup / "applied.json", 0o644)

    for name, mode in (("fullchain.pem", 0o644), ("privkey.pem", 0o600)):
        source = MIHOMO_TLS_DIR / name
        if source.is_file():
            _copy_atomic(source, backup / name, mode)

    return backup

def _write_applied_meta(meta: dict) -> None:
    MIHOMO_APPLIED_META.parent.mkdir(parents=True, exist_ok=True)
    temporary = MIHOMO_APPLIED_META.with_name(MIHOMO_APPLIED_META.name + ".new")
    temporary.write_text(
        json.dumps(meta, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    os.chown(temporary, 0, 0)
    os.chmod(temporary, 0o644)
    os.replace(temporary, MIHOMO_APPLIED_META)


def _sync_tls(meta: dict) -> None:
    settings = meta.get("settings") or {}
    need_tls = bool(
        settings.get("anytls_enabled") or settings.get("tuic_enabled")
    )
    if not need_tls:
        return

    domain = str(settings.get("domain") or "").strip().lower()
    if not domain:
        raise MihomoError("TLS-домен не задан")

    source_dir = Path(f"/etc/letsencrypt/live/{domain}")
    certificate = source_dir / "fullchain.pem"
    private_key = source_dir / "privkey.pem"
    if not certificate.is_file() or not private_key.is_file():
        raise MihomoError(
            "Сертификат Security не найден. Сначала получите Let's Encrypt."
        )

    _prepare_runtime_dirs()
    _copy_atomic(
        certificate,
        MIHOMO_TLS_DIR / "fullchain.pem",
        0o644,
    )
    _copy_atomic(
        private_key,
        MIHOMO_TLS_DIR / "privkey.pem",
        0o600,
    )


def _test(path: Path) -> str:
    if not MIHOMO_BINARY.is_file():
        raise MihomoError("Mihomo binary не установлен")

    _prepare_runtime_dirs()
    result = _run(
        [
            str(MIHOMO_BINARY),
            "-t",
            "-d",
            str(MIHOMO_STATE_DIR),
            "-f",
            str(path),
        ],
        timeout=60,
    )
    output = (result.stdout or result.stderr).strip()
    return output or "Mihomo configuration test passed"


def _configure_local_firewall(meta: dict) -> None:
    if shutil.which("ufw") is None:
        return

    status = subprocess.run(
        ["ufw", "status"],
        capture_output=True,
        text=True,
        check=False,
    )
    if "Status: active" not in status.stdout:
        return

    settings = meta.get("settings") or {}
    rules: list[tuple[int, str]] = []

    if settings.get("mieru_enabled"):
        rules.append(
            (
                int(settings.get("mieru_port", 2099)),
                str(settings.get("mieru_transport", "TCP")).lower(),
            )
        )
    if settings.get("anytls_enabled"):
        rules.append((int(settings.get("anytls_port", 8443)), "tcp"))
    if settings.get("tuic_enabled"):
        rules.append((int(settings.get("tuic_port", 10443)), "udp"))

    for port, transport in rules:
        _run(["ufw", "allow", f"{port}/{transport}"], timeout=30)


def _restore(backup: Path) -> bool:
    _prepare_runtime_dirs()

    previous = backup / "config.yaml"
    if previous.is_file():
        _copy_atomic(previous, MIHOMO_CONFIG, 0o600)
        has_config = True
    else:
        MIHOMO_CONFIG.unlink(missing_ok=True)
        has_config = False

    previous_meta = backup / "applied.json"
    if previous_meta.is_file():
        _copy_atomic(previous_meta, MIHOMO_APPLIED_META, 0o644)
    else:
        MIHOMO_APPLIED_META.unlink(missing_ok=True)

    for name, mode in (("fullchain.pem", 0o644), ("privkey.pem", 0o600)):
        source = backup / name
        target = MIHOMO_TLS_DIR / name
        if source.is_file():
            _copy_atomic(source, target, mode)
        else:
            target.unlink(missing_ok=True)

    return has_config

def _recover_service(has_config: bool) -> None:
    if has_config:
        subprocess.run(
            ["systemctl", "restart", "mihomo.service"],
            capture_output=True,
            text=True,
            check=False,
        )
    else:
        subprocess.run(
            ["systemctl", "stop", "mihomo.service"],
            capture_output=True,
            text=True,
            check=False,
        )


def apply_candidate() -> dict:
    if not MIHOMO_CANDIDATE.is_file():
        raise MihomoError("Mihomo candidate не найден")

    meta = _meta()
    protocols = [str(item) for item in (meta.get("protocols") or [])]
    backup = _backup_current()

    try:
        if not protocols:
            subprocess.run(
                ["systemctl", "stop", "mihomo.service"],
                capture_output=True,
                text=True,
                timeout=60,
                check=False,
            )
            subprocess.run(
                ["systemctl", "disable", "mihomo.service"],
                capture_output=True,
                text=True,
                timeout=60,
                check=False,
            )
            MIHOMO_CONFIG.unlink(missing_ok=True)
            _write_applied_meta(meta)
            return _result(
                True,
                "Все Mihomo listener выключены; служба остановлена",
                backup=backup.name,
                protocols=[],
            )

        _sync_tls(meta)
        _test(MIHOMO_CANDIDATE)
        _copy_atomic(MIHOMO_CANDIDATE, MIHOMO_CONFIG, 0o600)

        _run(["systemctl", "daemon-reload"])
        _run(["systemctl", "enable", "mihomo.service"])
        _run(["systemctl", "restart", "mihomo.service"])
        _run(["systemctl", "is-active", "--quiet", "mihomo.service"])
        _configure_local_firewall(meta)
        _write_applied_meta(meta)

        return _result(
            True,
            (
                "Mihomo configuration применена; "
                f"устройств: {meta.get('client_count', 0)}; "
                f"протоколы: {', '.join(protocols)}"
            ),
            backup=backup.name,
            protocols=protocols,
        )
    except Exception:
        restored = _restore(backup)
        _recover_service(restored)
        raise

def test_candidate() -> dict:
    if not MIHOMO_CANDIDATE.is_file():
        raise MihomoError("Mihomo candidate не найден")

    meta = _meta()
    protocols = [str(item) for item in (meta.get("protocols") or [])]
    if not protocols:
        return _result(True, "Все Mihomo listener будут выключены")

    backup = _backup_current()
    try:
        _sync_tls(meta)
        message = _test(MIHOMO_CANDIDATE)
        return _result(True, message)
    finally:
        _restore(backup)

def restart_service() -> dict:
    if not MIHOMO_CONFIG.is_file():
        raise MihomoError("Рабочая конфигурация Mihomo ещё не применена")

    _test(MIHOMO_CONFIG)
    _run(["systemctl", "restart", "mihomo.service"])
    _run(["systemctl", "is-active", "--quiet", "mihomo.service"])
    return _result(True, "mihomo.service перезапущен")

def rollback_latest() -> dict:
    _prepare_runtime_dirs()
    backups = [
        item
        for item in sorted(MIHOMO_BACKUP_DIR.glob("*"), reverse=True)
        if item.is_dir()
    ]
    if not backups:
        raise MihomoError("Нет резервной конфигурации Mihomo")

    selected = backups[0]
    insurance = _backup_current()

    try:
        restored = _restore(selected)
        if restored:
            _test(MIHOMO_CONFIG)
            _run(["systemctl", "restart", "mihomo.service"])
            _run(["systemctl", "is-active", "--quiet", "mihomo.service"])
        else:
            _run(["systemctl", "stop", "mihomo.service"])

        return _result(
            True,
            (
                f"Восстановлена конфигурация {selected.name}; "
                f"страховочная копия: {insurance.name}"
            ),
        )
    except Exception:
        restored = _restore(insurance)
        _recover_service(restored)
        raise

def main() -> int:
    action = sys.argv[1] if len(sys.argv) > 1 else ""

    try:
        _require_root()
        if action == "apply":
            payload = apply_candidate()
        elif action == "test":
            payload = test_candidate()
        elif action == "restart":
            payload = restart_service()
        elif action == "rollback":
            payload = rollback_latest()
        else:
            raise MihomoError(
                "Допустимые действия: apply, test, restart, rollback"
            )
    except Exception as exc:
        print(json.dumps(_result(False, str(exc)), ensure_ascii=False))
        return 1

    print(json.dumps(payload, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
