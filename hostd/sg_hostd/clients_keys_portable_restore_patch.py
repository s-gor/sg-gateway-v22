from __future__ import annotations

import json
import sqlite3
import tarfile
import tempfile
from functools import wraps
from pathlib import Path
from types import ModuleType

from sg_hostd import clients_keys_tls_backup_patch as tls_backup_patch


def _is_clients_keys_restore(full: ModuleType, archive: Path) -> bool:
    try:
        with tarfile.open(archive, "r:gz") as tar:
            member = tar.getmember("manifest.json")
            stream = tar.extractfile(member)
            if stream is None:
                return False
            manifest = json.loads(stream.read().decode("utf-8"))
    except (OSError, KeyError, tarfile.TarError, ValueError, json.JSONDecodeError):
        return False
    return bool(
        isinstance(manifest, dict)
        and manifest.get("format") == full.FORMAT
        and int(manifest.get("format_version") or 0) == full.FORMAT_VERSION
        and manifest.get("clients_keys_profile") is True
    )


def _apply_portable_clients_runtime_required(full: ModuleType) -> None:
    python = Path("/opt/sg-gateway/.venv/bin/python")
    if not python.is_file():
        raise RuntimeError("SG-Gateway venv Python is missing")
    code = (
        "import json,sys; "
        "from sg_hostd.client_runtime import apply_all_clients; "
        "r=apply_all_clients(); "
        "print(json.dumps(r,ensure_ascii=False,indent=2,default=str)); "
        "sys.exit(0 if r.get('ok') else 1)"
    )
    result = full._probe(
        [str(python), "-c", code],
        timeout=420,
        env=full._runtime_subprocess_env(),
    )
    output = (result.stdout or result.stderr or "").strip()
    if output:
        print(output[-16000:], flush=True)
    if result.returncode != 0:
        detail = output[-3200:]
        raise RuntimeError("Portable Clients & Keys runtime apply failed: " + detail)


def _restore_clients_keys(full: ModuleType, hard: ModuleType) -> dict:
    full._ensure_dirs()
    archive = full._backup_dir() / full.RESTORE_UPLOAD_NAME
    if not archive.is_file():
        raise RuntimeError("Uploaded .sgbackup file not found")

    full._restore_progress(
        "[Restore 1/8] Проверяю Clients & Keys backup и свободное место"
    )
    plan = hard._preflight_full_restore(full, archive)
    full._restore_progress(
        "[Restore 1/8] Места достаточно: свободно "
        f"{hard._format_bytes(plan['free_bytes'])}; безопасный минимум "
        f"{hard._format_bytes(plan['required_free_bytes'])}"
    )

    with tempfile.TemporaryDirectory(
        prefix="restore-clients-",
        dir=full._work_dir(),
    ) as temp_name:
        temp = Path(temp_name)
        manifest = full._extract_archive(archive, temp)
        if manifest.get("clients_keys_profile") is not True:
            raise RuntimeError(
                "Uploaded backup is not a Clients & Keys restore profile"
            )
        payload = temp / "payload"
        db_path = (
            payload
            / full._data_dir().relative_to("/")
            / "sg-gateway.sqlite"
        )
        if not db_path.is_file():
            raise RuntimeError("Backup does not contain the SG-Gateway database")
        db = sqlite3.connect(db_path)
        try:
            row = db.execute("PRAGMA integrity_check").fetchone()
            if not row or str(row[0]).lower() != "ok":
                raise RuntimeError("Uploaded SQLite database is damaged")
        finally:
            db.close()

        full._restore_progress(
            "[Restore 2/8] Backup и SQLite проверены; выключенные протоколы "
            "нового сервера будут пропущены"
        )
        full._restore_progress(
            "[Restore 3/8] Создаю страховочный Full Backup текущего сервера"
        )
        safety = full.create_full_backup_archive(prefix="SG-Gateway-SAFETY")

        try:
            full._restore_progress(
                "[Restore 4/8] Восстанавливаю клиентов, ключи и переносимый HTTPS"
            )
            full._restore_payload(payload, preserve_machine_env=True)
            full._restore_progress(
                "[Restore 5/8] Проверяю SQLite и права; настройки нового "
                "сервера сохранены"
            )
            full._normalize_panel_data_permissions()
            full._validate_database_as_panel_user()

            full._restore_progress(
                "[Restore 6/8] Возвращаю HTTPS и пересобираю только "
                "разрешённый runtime нового сервера"
            )
            cert_ready, cert_domain = full._restored_certificate_ready()
            if cert_domain:
                state = full._restored_tls_state()
                panel_port = int(
                    state.get("public_port")
                    or state.get("panel_port")
                    or 443
                )
                suffix = "" if panel_port == 443 else f":{panel_port}"
                full._restore_progress(
                    f"[Restore 6/8] Адрес панели после переключения: "
                    f"https://{cert_domain}{suffix}"
                )

            live_database = full._data_dir() / "sg-gateway.sqlite"
            with tls_backup_patch.destination_protocol_policy(live_database):
                if cert_domain:
                    full._refresh_restored_https_from_local_files(
                        allow_xray_inactive=True
                    )
                _apply_portable_clients_runtime_required(full)

            full._validate_runtime_after_restore()
            cert_ready, cert_domain = full._restored_certificate_ready()
            if cert_domain and not cert_ready:
                raise RuntimeError(
                    f"Restored certificate validation failed for {cert_domain}"
                )

            full._restore_progress(
                "[Restore 7/8] Проверяю backend, HTTPS и hostd до restart панели"
            )
            hard._local_panel_health(full)
            panel_generation = hard._panel_service_generation(full)
            hard._schedule_panel_restart_required(full)
            full._restore_progress(
                "[Restore 7/8] Панель перезапускается; жду новый процесс и "
                "post-restart health-check"
            )
            hard._wait_for_panel_after_scheduled_restart(
                full,
                panel_generation,
            )
            full._restore_progress(
                "[Restore 8/8] Восстановление клиентов, ключей и HTTPS "
                "завершено: настройки и выключенные протоколы нового сервера "
                "сохранены"
            )
        except Exception as restore_exc:
            full._restore_progress(
                f"[Restore] ОШИБКА: {restore_exc}. Автоматически возвращаю "
                "страховочный backup"
            )
            safety_path = Path(str(safety["path"]))
            try:
                with tempfile.TemporaryDirectory(
                    prefix="rollback-",
                    dir=full._work_dir(),
                ) as rollback_name:
                    rollback = Path(rollback_name)
                    full._extract_archive(safety_path, rollback)
                    full._restore_payload(
                        rollback / "payload",
                        preserve_machine_env=False,
                    )
                    full._normalize_panel_data_permissions()
                    full._validate_runtime_after_restore()
                    full._restart_runtime(schedule_panel=False)
                    hard._local_panel_health(full)
                rollback_panel_generation = hard._panel_service_generation(full)
                hard._schedule_panel_restart_required(full)
                full._restore_progress(
                    "[Restore] Safety Rollback: панель перезапускается; "
                    "жду новый процесс и post-restart health-check"
                )
                hard._wait_for_panel_after_scheduled_restart(
                    full,
                    rollback_panel_generation,
                )
            except Exception as rollback_exc:
                full._restore_progress(
                    f"[Restore] КРИТИЧЕСКАЯ ОШИБКА: Safety Rollback не прошёл "
                    f"проверку: {rollback_exc}"
                )
                raise RuntimeError(
                    "Восстановление клиентов и ключей завершилось ошибкой, и "
                    "автоматический Safety Rollback также не прошёл проверку. "
                    f"Restore: {restore_exc}; Rollback: {rollback_exc}"
                ) from rollback_exc

            full._restore_progress(
                "[Restore] Safety Rollback выполнен и проверен после restart: "
                "SQLite, runtime и новый процесс панели доступны"
            )
            raise RuntimeError(
                "Восстановление клиентов и ключей завершилось ошибкой; "
                "Safety Rollback выполнен и проверен после restart. "
                f"Причина Restore: {restore_exc}"
            ) from restore_exc

    archive.unlink(missing_ok=True)
    cert_ready, cert_domain = full._restored_certificate_ready()
    return {
        "source_version": str(manifest.get("source_version") or "unknown"),
        "safety_backup": str(safety.get("name") or ""),
        "certificates": cert_ready,
        "certificate_domain": cert_domain,
        "certificate_policy": str(
            manifest.get("certificate_policy") or "none"
        ),
        "xray_active": full._probe(
            ["systemctl", "is-active", "--quiet", "xray.service"],
            timeout=20,
        ).returncode
        == 0,
        "client_runtime_applied": True,
        "portable_runtime_regenerated": True,
        "restore_space_preflight": plan,
        "panel_health_validated": True,
        "panel_post_restart_health_validated": True,
        "panel_restart_generation_changed": True,
        "restore_profile": "clients-and-keys",
        "destination_protocol_enablement_preserved": True,
        "message": (
            "Clients & Keys restored; destination server settings and protocol "
            "enablement preserved; HTTPS identity restored when compatible; "
            "new panel process validated after restart"
        ),
    }


def install(hard: ModuleType, full: ModuleType) -> None:
    if getattr(full, "_clients_keys_portable_restore_v2_installed", False):
        return

    # Wrap only the public restore entry point. The hardened Full Restore
    # implementation remains untouched and is still used byte-for-byte for
    # every non-Clients&Keys archive. functools.wraps deliberately preserves
    # the established restore_hardening_patch identity/metadata.
    original = full.restore_uploaded_full_backup

    @wraps(original)
    def dispatch() -> dict:
        archive = full._backup_dir() / full.RESTORE_UPLOAD_NAME
        if _is_clients_keys_restore(full, archive):
            return _restore_clients_keys(full, hard)
        return original()

    full.restore_uploaded_full_backup = dispatch
    full._clients_keys_portable_restore_v2_installed = True
