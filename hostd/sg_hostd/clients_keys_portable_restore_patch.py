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
    ready engines from being reconciled. Credentials for deferred engines stay
    dormant after restore; their original material is preserved byte-for-byte
    and can be reactivated by a later successful runtime reconcile.
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
            deferred_ids = {row_id for row_id, _status in snapshots}
            for row_id, status in snapshots:
                if row_id in deferred_ids and status == "applied":
                    continue
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
