from __future__ import annotations

import json
import sqlite3
import tarfile
import tempfile
from contextlib import contextmanager
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


def _apply_portable_clients_runtime_required(full: ModuleType) -> dict:
    """Best-effort runtime reconcile after durable Clients & Keys restore.

    Runtime/Connection readiness belongs to the destination server and is not
    part of backup integrity. A missing runtime therefore leaves the restored
    identity dormant instead of rolling the database back.
    """

    python = Path("/opt/sg-gateway/.venv/bin/python")
    if not python.is_file():
        return {
            "ok": False,
            "deferred": True,
            "error": "SG-Gateway venv Python is missing",
        }
    code = (
        "import json,sys; "
        "from sg_hostd.client_runtime import apply_all_clients; "
        "r=apply_all_clients(); "
        "print(json.dumps(r,ensure_ascii=False,indent=2,default=str)); "
        "sys.exit(0 if r.get('ok') else 1)"
    )
    runtime_env = dict(full._runtime_subprocess_env())
    runtime_env["SG_GATEWAY_CLIENTS_KEYS_RESTORE"] = "1"
    result = full._probe(
        [str(python), "-c", code],
        timeout=420,
        env=runtime_env,
    )
    output = (result.stdout or result.stderr or "").strip()
    if output:
        print(output[-16000:], flush=True)
    payload: dict = {}
    if output:
        try:
            decoded = json.loads(output)
            if isinstance(decoded, dict):
                payload = decoded
        except (TypeError, ValueError, json.JSONDecodeError):
            payload = {}
    if result.returncode != 0 or payload.get("ok") is False:
        return {
            "ok": False,
            "deferred": True,
            "error": output[-3200:] or "Portable Clients & Keys runtime apply deferred",
        }
    payload.setdefault("ok", True)
    payload["deferred"] = any(
        isinstance(item, dict) and bool(item.get("deferred"))
        for item in payload.get("engines", [])
    )
    return payload


@contextmanager
def _destination_runtime_policy(database_path: Path):
    """Temporarily hide only credentials whose destination runtime is absent.

    `apply_all_clients()` intentionally uses a global Runtime Contract for
    ordinary client mutations. Portable restore is different: durable access
    has already been validated, so a missing runtime must not prevent other
    ready engines from being reconciled. Original credential statuses are
    restored byte-for-byte after the best-effort runtime pass.
    """

    from sg_hostd import runtime_contracts

    contract = runtime_contracts.inspect_runtime_contract(
        database_path=database_path,
        strict_optional=False,
        include_all_critical=False,
    )
    deferred_engines = sorted(
        {
            str(item.get("engine") or "").strip().lower()
            for item in contract.get("failures", [])
            if str(item.get("engine") or "").strip()
        }
    )
    if not deferred_engines:
        yield {"deferred_engines": [], "runtime_contract": contract}
        return

    database = sqlite3.connect(database_path, timeout=15)
    snapshots: list[tuple[int, str]] = []
    try:
        placeholders = ",".join("?" for _ in deferred_engines)
        rows = database.execute(
            f"SELECT id, status FROM device_credentials WHERE lower(engine) IN ({placeholders})",
            tuple(deferred_engines),
        ).fetchall()
        snapshots = [(int(row_id), str(status)) for row_id, status in rows]
        for row_id, _status in snapshots:
            database.execute(
                "UPDATE device_credentials SET status = 'disabled' WHERE id = ?",
                (row_id,),
            )
        database.commit()
        yield {
            "deferred_engines": deferred_engines,
            "runtime_contract": contract,
        }
    finally:
        try:
            for row_id, status in snapshots:
                database.execute(
                    "UPDATE device_credentials SET status = ? WHERE id = ?",
                    (status, row_id),
                )
            database.commit()
        finally:
            database.close()


def _validate_portable_runtime_best_effort(full: ModuleType) -> dict:
    try:
        full._validate_runtime_after_restore()
    except Exception as exc:
        return {"ok": False, "deferred": True, "error": str(exc)}
    return {"ok": True, "deferred": False}


def _install_destination_runtime_contract_defer() -> None:
    """Do not let destination runtime readiness reject a valid portable backup."""

    if getattr(tls_backup_patch, "_dormant_runtime_contract_installed", False):
        return
    original = tls_backup_patch._runtime_contract_for_destination

    @wraps(original)
    def deferred(data: ModuleType, database_path: Path) -> dict:
        try:
            return original(data, database_path)
        except Exception as exc:
            if exc.__class__.__name__ != "RuntimeContractError":
                raise
            return {
                "ok": False,
                "deferred": True,
                "checks": [],
                "profile": "clients-and-keys",
                "disabled_destination_protocols_skipped": True,
                "error": str(exc),
            }

    tls_backup_patch._runtime_contract_for_destination = deferred
    tls_backup_patch._dormant_runtime_contract_installed = True


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
        runtime_result: dict = {"ok": False, "deferred": True}
        runtime_validation: dict = {"ok": False, "deferred": True}
        deferred_engines: list[str] = []

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
                with _destination_runtime_policy(live_database) as runtime_policy:
                    deferred_engines = list(runtime_policy["deferred_engines"])
                    if cert_domain:
                        full._refresh_restored_https_from_local_files(
                            allow_xray_inactive=True
                        )
                    runtime_result = _apply_portable_clients_runtime_required(full)

            runtime_deferred_engines = [
                str(item.get("engine") or "").strip().lower()
                for item in runtime_result.get("engines", [])
                if isinstance(item, dict)
                and item.get("deferred")
                and str(item.get("engine") or "").strip()
            ]
            deferred_engines = sorted(
                set(deferred_engines) | set(runtime_deferred_engines)
            )
            runtime_validation = _validate_portable_runtime_best_effort(full)
            cert_ready, cert_domain = full._restored_certificate_ready()
            if (
                deferred_engines
                or runtime_result.get("deferred")
                or runtime_validation.get("deferred")
            ):
                full._restore_progress(
                    "[Restore 6/8] Клиенты и ключи восстановлены; часть runtime "
                    "пока не готова и останется dormant до включения Connections"
                )
            if cert_domain and not cert_ready:
                full._restore_progress(
                    f"[Restore 6/8] HTTPS для {cert_domain} пока не готов; "
                    "TLS-зависимые профили останутся dormant"
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
                    rollback_cert_ready, rollback_cert_domain = (
                        full._restored_certificate_ready()
                    )
                    if rollback_cert_domain:
                        full._refresh_restored_https_from_local_files(
                            allow_xray_inactive=True
                        )
                    full._validate_runtime_after_restore()
                    full._restart_runtime(schedule_panel=False)
                    if rollback_cert_domain:
                        full._refresh_restored_https_from_local_files(
                            allow_xray_inactive=True
                        )
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
        "client_runtime_applied": bool(runtime_result.get("ok")),
        "client_runtime_deferred": bool(
            deferred_engines
            or runtime_result.get("deferred")
            or runtime_validation.get("deferred")
        ),
        "client_runtime_deferred_engines": deferred_engines,
        "portable_runtime_regenerated": bool(runtime_result.get("ok")),
        "restore_space_preflight": plan,
        "panel_health_validated": True,
        "panel_post_restart_health_validated": True,
        "panel_restart_generation_changed": True,
        "restore_profile": "clients-and-keys",
        "destination_protocol_enablement_preserved": True,
        "message": (
            "Clients & Keys restored; destination server settings and protocol "
            "enablement preserved; unavailable runtime/profiles remain dormant "
            "until their Connections become ready"
        ),
    }


def install(hard: ModuleType, full: ModuleType) -> None:
    if getattr(full, "_clients_keys_portable_restore_v2_installed", False):
        return

    _install_destination_runtime_contract_defer()

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
