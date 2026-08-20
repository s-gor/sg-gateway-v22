from __future__ import annotations

import json
import os
import shutil
import sqlite3
import tarfile
import tempfile
import time
from pathlib import Path
from types import ModuleType


# The uploaded archive is already present on disk. Extra free space is needed
# for its unpacked payload, the persistent Safety archive and a possible Safety
# rollback extraction. Keep a fixed emergency margin on top of that estimate.
RESTORE_MARGIN_MIN_BYTES = 128 * 1024 * 1024
RESTORE_MARGIN_RATIO = 0.10
PANEL_RESTART_GRACE_SECONDS = 4.0
PANEL_RESTART_HEALTH_TIMEOUT_SECONDS = 45.0
PANEL_RESTART_HEALTH_POLL_SECONDS = 1.0


def _format_bytes(value: int) -> str:
    size = float(max(0, int(value)))
    units = ("B", "KiB", "MiB", "GiB", "TiB")
    for unit in units:
        if size < 1024 or unit == units[-1]:
            return f"{size:.1f} {unit}" if unit != "B" else f"{int(size)} B"
        size /= 1024
    return f"{int(value)} B"


def _excluded_history(full: ModuleType, path: Path) -> bool:
    return bool(
        path.name in getattr(full, "TRANSIENT_SECURITY_DIRS", set())
        and path.parent.name == "security"
    )


def _tree_bytes(full: ModuleType, path: Path) -> int:
    try:
        if _excluded_history(full, path):
            return 0
        stat = path.lstat()
    except OSError:
        return 0

    if path.is_symlink():
        return max(0, int(stat.st_size))
    if path.is_file():
        return max(0, int(stat.st_size))
    if not path.is_dir():
        return 0

    total = 0
    try:
        with os.scandir(path) as entries:
            for entry in entries:
                total += _tree_bytes(full, Path(entry.path))
    except OSError:
        pass
    return total


def _current_portable_state_bytes(full: ModuleType) -> int:
    roots, data_paths = full._archive_sources()
    total = sum(_tree_bytes(full, path) for path in roots)
    total += sum(_tree_bytes(full, path) for path in data_paths)
    total += _tree_bytes(full, full._data_dir() / "sg-gateway.sqlite")
    return max(0, int(total))


def _archive_unpacked_bytes(full: ModuleType, archive: Path) -> int:
    # Read and validate headers only. This must happen before extraction so a
    # valid but very large archive cannot fill the destination disk first.
    with tarfile.open(archive, "r:gz") as tar:
        members = [
            member
            for member in tar.getmembers()
            if not full._is_internal_history_member(member.name)
        ]
        preview_root = full._work_dir() / ".restore-preflight"
        full._validate_members(tar, preview_root, members)
        return sum(
            max(0, int(member.size))
            for member in members
            if member.isfile()
        )


def _restore_space_plan(full: ModuleType, archive: Path) -> dict[str, int]:
    unpacked = _archive_unpacked_bytes(full, archive)
    current = _current_portable_state_bytes(full)
    working = unpacked + (2 * current)
    margin = max(
        RESTORE_MARGIN_MIN_BYTES,
        int(working * RESTORE_MARGIN_RATIO),
    )
    required = working + margin
    free = int(shutil.disk_usage(str(full._data_dir())).free)
    return {
        "archive_unpacked_bytes": unpacked,
        "current_state_bytes": current,
        "margin_bytes": margin,
        "required_free_bytes": required,
        "free_bytes": free,
    }


def _preflight_full_restore(full: ModuleType, archive: Path) -> dict[str, int]:
    plan = _restore_space_plan(full, archive)
    free = int(plan["free_bytes"])
    required = int(plan["required_free_bytes"])
    if free < required:
        raise RuntimeError(
            "Недостаточно свободного места для безопасного Full Restore: "
            f"свободно {_format_bytes(free)}, требуется не менее "
            f"{_format_bytes(required)}. Сервер не изменён."
        )
    return plan


def _local_panel_health(full: ModuleType) -> None:
    curl = shutil.which("curl")
    if not curl:
        raise RuntimeError("Cannot validate panel health after restore: curl missing")

    sg_env = full._read_env(full.CONFIG_DIR / "sg-gateway.env")
    runtime_env = full._read_env(full.CONFIG_DIR / "runtime.env")
    try:
        backend_port = int(sg_env.get("SG_GATEWAY_PORT") or 18080)
    except (TypeError, ValueError):
        backend_port = 18080

    backend = full._probe(
        [curl, "-fsS", "--max-time", "8", f"http://127.0.0.1:{backend_port}/health"],
        timeout=12,
    )
    if backend.returncode != 0:
        detail = (backend.stderr or backend.stdout or "").strip()[-800:]
        raise RuntimeError("Panel backend health check failed: " + detail)
    try:
        payload = json.loads(backend.stdout or "{}")
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise RuntimeError("Panel backend returned invalid health JSON") from exc
    if not isinstance(payload, dict) or payload.get("status") != "ok":
        raise RuntimeError("Panel backend health status is not ok")

    nginx_active = full._probe(
        ["systemctl", "is-active", "--quiet", "nginx.service"], timeout=15
    )
    if nginx_active.returncode != 0:
        raise RuntimeError("Nginx is not active after restore")

    cert_ready, cert_domain = full._restored_certificate_ready()
    if not cert_domain:
        return
    if not cert_ready:
        raise RuntimeError(f"Certificate health check failed for {cert_domain}")

    state = full._restored_tls_state()
    raw_port = (
        state.get("public_port")
        or state.get("panel_port")
        or runtime_env.get("SG_GATEWAY_PANEL_PORT")
        or sg_env.get("SG_GATEWAY_PUBLIC_PORT")
        or 443
    )
    try:
        panel_port = int(raw_port)
    except (TypeError, ValueError):
        panel_port = 443
    suffix = "" if panel_port == 443 else f":{panel_port}"
    local_https = full._probe(
        [
            curl,
            "-kfsS",
            "--max-time",
            "10",
            "--resolve",
            f"{cert_domain}:{panel_port}:127.0.0.1",
            f"https://{cert_domain}{suffix}/health",
        ],
        timeout=15,
    )
    if local_https.returncode != 0:
        detail = (local_https.stderr or local_https.stdout or "").strip()[-800:]
        raise RuntimeError("Local HTTPS health check failed: " + detail)
    try:
        payload = json.loads(local_https.stdout or "{}")
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise RuntimeError("Local HTTPS returned invalid health JSON") from exc
    if not isinstance(payload, dict) or payload.get("status") != "ok":
        raise RuntimeError("Local HTTPS health status is not ok")


def _panel_service_generation(full: ModuleType) -> int:
    result = full._probe(
        [
            "systemctl",
            "show",
            "sg-gateway.service",
            "--property=ActiveEnterTimestampMonotonic",
            "--value",
        ],
        timeout=10,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()[-800:]
        raise RuntimeError("Cannot read panel service generation: " + detail)
    try:
        generation = int((result.stdout or "").strip())
    except (TypeError, ValueError) as exc:
        raise RuntimeError("Panel service generation is invalid") from exc
    if generation <= 0:
        raise RuntimeError("Panel service is not active before restart")
    return generation


def _schedule_panel_restart_required(full: ModuleType) -> None:
    unit = (
        f"sg-gateway-full-restore-restart-{os.getpid()}-"
        f"{time.monotonic_ns()}"
    )
    result = full._probe(
        [
            "systemd-run",
            f"--unit={unit}",
            "--collect",
            "--on-active=3s",
            "/bin/systemctl",
            "restart",
            "sg-hostd.service",
            "sg-gateway.service",
        ],
        timeout=15,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()[-800:]
        raise RuntimeError("Cannot schedule required panel restart: " + detail)


def _wait_for_panel_after_scheduled_restart(
    full: ModuleType,
    previous_generation: int,
) -> None:
    # A health response alone is insufficient: if the scheduled restart failed,
    # it could still come from the old process. Require systemd's active-enter
    # generation to change first, then validate backend + Nginx/HTTPS.
    time.sleep(PANEL_RESTART_GRACE_SECONDS)
    deadline = time.monotonic() + PANEL_RESTART_HEALTH_TIMEOUT_SECONDS
    last_error: Exception | None = None
    while True:
        try:
            generation = _panel_service_generation(full)
            if generation == previous_generation:
                raise RuntimeError("Panel service has not restarted yet")
            _local_panel_health(full)
            return
        except Exception as exc:
            last_error = exc
        if time.monotonic() >= deadline:
            raise RuntimeError(
                "Panel did not become healthy after required restart: "
                f"{last_error}"
            ) from last_error
        time.sleep(PANEL_RESTART_HEALTH_POLL_SECONDS)


def _restore_uploaded_full_backup(full: ModuleType) -> dict:
    full._ensure_dirs()
    archive = full._backup_dir() / full.RESTORE_UPLOAD_NAME
    if not archive.is_file():
        raise RuntimeError("Uploaded .sgbackup file not found")

    # Preflight must happen before unpacking and before the Safety Backup.
    full._restore_progress("[Restore 1/8] Проверяю структуру .sgbackup и свободное место")
    plan = _preflight_full_restore(full, archive)
    full._restore_progress(
        "[Restore 1/8] Места достаточно: свободно "
        f"{_format_bytes(plan['free_bytes'])}; безопасный минимум "
        f"{_format_bytes(plan['required_free_bytes'])}"
    )

    with tempfile.TemporaryDirectory(prefix="restore-", dir=full._work_dir()) as temp_name:
        temp = Path(temp_name)
        manifest = full._extract_archive(archive, temp)
        clients_keys_profile = bool(manifest.get("clients_keys_profile") is True)
        restore_profile = "clients-and-keys" if clients_keys_profile else "full"
        restore_done = (
            "Восстановление клиентов и ключей завершено"
            if clients_keys_profile
            else "Full Restore завершён"
        )
        restore_failed = (
            "Восстановление клиентов и ключей завершилось ошибкой"
            if clients_keys_profile
            else "Full Restore завершился ошибкой"
        )
        payload = temp / "payload"
        db_path = payload / full._data_dir().relative_to("/") / "sg-gateway.sqlite"
        if not db_path.is_file():
            raise RuntimeError("Backup does not contain the SG-Gateway database")
        db = sqlite3.connect(db_path)
        try:
            row = db.execute("PRAGMA integrity_check").fetchone()
            if not row or str(row[0]).lower() != "ok":
                raise RuntimeError("Uploaded SQLite database is damaged")
        finally:
            db.close()

        from sg_hostd.runtime_contracts import assert_runtime_contract

        assert_runtime_contract(
            database_path=db_path,
            strict_optional=True,
            include_all_critical=True,
        )
        full._restore_progress("[Restore 2/8] Backup, SQLite и Runtime Contract проверены")
        full._restore_progress("[Restore 3/8] Создаю страховочный Full Backup текущего сервера")
        safety = full.create_full_backup_archive(prefix="SG-Gateway-SAFETY")

        try:
            full._restore_progress("[Restore 4/8] Восстанавливаю данные и переносимое состояние")
            full._restore_payload(payload, preserve_machine_env=True)
            full._restore_progress("[Restore 5/8] Проверяю SQLite и права доступа")
            full._normalize_panel_data_permissions()
            full._validate_database_as_panel_user()

            full._restore_progress("[Restore 6/8] Возвращаю HTTPS и пересобираю runtime на целевом сервере")
            cert_ready, cert_domain = full._restored_certificate_ready()
            if cert_domain:
                state = full._restored_tls_state()
                panel_port = int(state.get("public_port") or state.get("panel_port") or 443)
                suffix = "" if panel_port == 443 else f":{panel_port}"
                full._restore_progress(
                    f"[Restore 6/8] Адрес панели после переключения: "
                    f"https://{cert_domain}{suffix}"
                )
                full._refresh_restored_https_from_local_files(allow_xray_inactive=True)

            full._apply_client_runtime_required()
            full._normalize_xray_full_access()
            full._restart_xray_required()
            if cert_domain:
                full._refresh_restored_https_from_local_files(allow_xray_inactive=False)
                full._apply_client_runtime_required()
                full._normalize_xray_full_access()
                full._restart_xray_required()

            full._validate_runtime_after_restore()
            cert_ready, cert_domain = full._restored_certificate_ready()
            if cert_domain and not cert_ready:
                raise RuntimeError(
                    f"Restored certificate validation failed for {cert_domain}"
                )

            full._restore_progress("[Restore 7/8] Проверяю backend и Nginx/HTTPS до restart панели")
            _local_panel_health(full)
            panel_generation = _panel_service_generation(full)
            _schedule_panel_restart_required(full)
            full._restore_progress(
                "[Restore 7/8] Панель перезапускается; жду новый процесс и post-restart health-check"
            )
            _wait_for_panel_after_scheduled_restart(full, panel_generation)
            full._restore_progress(
                f"[Restore 8/8] {restore_done}: новый процесс панели и доступ после restart проверены"
            )
        except Exception as restore_exc:
            full._restore_progress(
                f"[Restore] ОШИБКА: {restore_exc}. Автоматически возвращаю страховочный backup"
            )
            safety_path = Path(str(safety["path"]))
            try:
                with tempfile.TemporaryDirectory(
                    prefix="rollback-", dir=full._work_dir()
                ) as rollback_name:
                    rollback = Path(rollback_name)
                    full._extract_archive(safety_path, rollback)
                    full._restore_payload(
                        rollback / "payload", preserve_machine_env=False
                    )
                    full._normalize_panel_data_permissions()
                    full._validate_runtime_after_restore()
                    full._restart_runtime(schedule_panel=False)
                    _local_panel_health(full)
                rollback_panel_generation = _panel_service_generation(full)
                _schedule_panel_restart_required(full)
                full._restore_progress(
                    "[Restore] Safety Rollback: панель перезапускается; "
                    "жду новый процесс и post-restart health-check"
                )
                _wait_for_panel_after_scheduled_restart(
                    full, rollback_panel_generation
                )
            except Exception as rollback_exc:
                full._restore_progress(
                    f"[Restore] КРИТИЧЕСКАЯ ОШИБКА: Safety Rollback не прошёл "
                    f"проверку: {rollback_exc}"
                )
                raise RuntimeError(
                    f"{restore_failed}, и автоматический Safety Rollback также "
                    f"не прошёл проверку. Restore: {restore_exc}; "
                    f"Rollback: {rollback_exc}"
                ) from rollback_exc

            full._restore_progress(
                "[Restore] Safety Rollback выполнен и проверен после restart: "
                "SQLite, runtime и новый процесс панели доступны"
            )
            raise RuntimeError(
                f"{restore_failed}; Safety Rollback выполнен и проверен после restart. "
                f"Причина Restore: {restore_exc}"
            ) from restore_exc

    archive.unlink(missing_ok=True)
    cert_ready, cert_domain = full._restored_certificate_ready()
    return {
        "source_version": str(manifest.get("source_version") or "unknown"),
        "safety_backup": str(safety.get("name") or ""),
        "certificates": cert_ready,
        "certificate_domain": cert_domain,
        "xray_active": full._probe(
            ["systemctl", "is-active", "--quiet", "xray.service"], timeout=20
        ).returncode
        == 0,
        "client_runtime_applied": True,
        "portable_runtime_regenerated": True,
        "restore_space_preflight": plan,
        "panel_health_validated": True,
        "panel_post_restart_health_validated": True,
        "panel_restart_generation_changed": True,
        "restore_profile": restore_profile,
        "message": (
            "Clients & Keys restored; destination server settings preserved; "
            "client runtime regenerated and new panel process validated after restart"
            if clients_keys_profile
            else "Full backup restored; destination public IP preserved; all runtime "
            "regenerated and new panel process validated after restart"
        ),
    }


def install(full: ModuleType) -> None:
    # Keep the implementation in a small additive module so the frozen stable
    # restore source is untouched while dev-02206 can be hardened and tested.
    def restore() -> dict:
        return _restore_uploaded_full_backup(full)

    full.restore_uploaded_full_backup = restore
    full.restore_space_plan = lambda archive: _restore_space_plan(full, Path(archive))
    full.validate_local_panel_health = lambda: _local_panel_health(full)
