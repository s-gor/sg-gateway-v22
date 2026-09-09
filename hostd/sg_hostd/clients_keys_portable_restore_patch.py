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
    """Keep destination-missing engine credentials dormant after restore.

    Portable Clients & Keys restore preserves durable credentials independently
    from destination runtime readiness. Engines that fail the destination
    runtime contract are disabled in `device_credentials` and intentionally
    stay disabled after the best-effort apply pass. Their key/config material is
    untouched; a later successful Connection/runtime reconcile can reactivate
    the same credential without regeneration.
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
    request = full._read_json(full.RESTORE_REQUEST_PATH)
    backup_name = full._validated_backup_name(str(request.get("backup_name") or ""))
    backup_path = full.BACKUP_DIR / backup_name
    if not backup_path.is_file():
        raise RuntimeError(f"Backup not found: {backup_name}")
    if not _is_clients_keys_restore(full, backup_path):
        raise RuntimeError("Selected backup is not a Clients & Keys portable backup")

    print("[Restore 1/8] Проверяю Clients & Keys backup и свободное место", flush=True)
    hard._verify_backup_archive(full, backup_path)
    hard._ensure_restore_free_space(full, backup_path)

    with tempfile.TemporaryDirectory(prefix="sg-gateway-clients-keys-restore-") as tmp:
        tmp_path = Path(tmp)
        full._extract_archive(backup_path, tmp_path)
        full._validate_extracted_backup(tmp_path)
        print("[Restore 2/8] Backup и SQLite проверены; выключенные протоколы нового сервера будут пропущены", flush=True)

        print("[Restore 3/8] Создаю страховочный Full Backup текущего сервера", flush=True)
        safety_backup = full.create_full_backup()
        safety_backup_name = str(safety_backup.get("backup") or "")
        if not safety_backup_name:
            raise RuntimeError("Safety backup was not created")
        safety_backup_path = full.BACKUP_DIR / safety_backup_name

        try:
            print("[Restore 4/8] Восстанавливаю клиентов, ключи и переносимый HTTPS", flush=True)
            restore_result = tls_backup_patch.restore_clients_keys_portable(full, tmp_path)

            print("[Restore 5/8] Проверяю SQLite и права; настройки нового сервера сохранены", flush=True)
            full._validate_database_after_restore()
            full._restore_permissions()

            print("[Restore 6/8] Возвращаю HTTPS и пересобираю только разрешённый runtime нового сервера", flush=True)
            tls_result = tls_backup_patch.restore_portable_https(full, tmp_path)
            database_path = Path(full.DB_PATH)
            with _destination_runtime_policy(database_path) as runtime_policy:
                runtime_result = _apply_portable_clients_runtime_required(full)
            runtime_validation = _validate_portable_runtime_best_effort(full)

            print("[Restore 7/8] Проверяю панель и сохранённые сервисы нового сервера", flush=True)
            hard._local_panel_health(full)

            print("[Restore 8/8] Восстановление клиентов и ключей завершено", flush=True)
            result = {
                "ok": True,
                "profile": "clients-and-keys",
                "backup": backup_name,
                "safety_backup": safety_backup_name,
                "restore": restore_result,
                "https": tls_result,
                "runtime": runtime_result,
                "runtime_policy": runtime_policy,
                "runtime_validation": runtime_validation,
            }
            return result
        except Exception as restore_exc:
            print(
                f"[Restore] ОШИБКА: {restore_exc}. Автоматически возвращаю страховочный backup",
                flush=True,
            )
            try:
                with tempfile.TemporaryDirectory(prefix="sg-gateway-clients-keys-rollback-") as rollback_tmp:
                    rollback_path = Path(rollback_tmp)
                    full._extract_archive(safety_backup_path, rollback_path)
                    full._validate_extracted_backup(rollback_path)
                    full._restore_full_from_extracted(rollback_path)
                hard._local_panel_health(full)
            except Exception as rollback_exc:
                raise RuntimeError(
                    "Восстановление клиентов и ключей завершилось ошибкой, и автоматический "
                    f"Safety Rollback также не прошёл проверку. Restore: {restore_exc}; "
                    f"Rollback: {rollback_exc}"
                ) from rollback_exc
            raise RuntimeError(
                f"Восстановление клиентов и ключей завершилось ошибкой. Safety Rollback выполнен. {restore_exc}"
            ) from restore_exc


def install(full: ModuleType, hard: ModuleType) -> None:
    _install_destination_runtime_contract_defer()
    if getattr(full, "_clients_keys_portable_restore_installed", False):
        return
    original = full.restore_uploaded_full_backup

    @wraps(original)
    def dispatch() -> dict:
        try:
            request = full._read_json(full.RESTORE_REQUEST_PATH)
            backup_name = full._validated_backup_name(str(request.get("backup_name") or ""))
            backup_path = full.BACKUP_DIR / backup_name
        except Exception:
            return original()
        if backup_path.is_file() and _is_clients_keys_restore(full, backup_path):
            return _restore_clients_keys(full, hard)
        return original()

    full.restore_uploaded_full_backup = dispatch
    full._clients_keys_portable_restore_installed = True
