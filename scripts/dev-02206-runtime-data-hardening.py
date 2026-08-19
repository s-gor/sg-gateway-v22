from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def write(path: str, body: str) -> None:
    target = ROOT / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(body, encoding="utf-8", newline="\n")


def replace_once(path: str, old: str, new: str, marker: str | None = None) -> None:
    body = read(path)
    if marker and marker in body:
        return
    if old not in body:
        raise SystemExit(f"anchor not found in {path}: {old[:120]!r}")
    body = body.replace(old, new, 1)
    write(path, body)


RUNTIME_CONTRACTS = r'''from __future__ import annotations

import os
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping


class RuntimeContractError(RuntimeError):
    pass


@dataclass(frozen=True)
class Requirement:
    label: str
    alternatives: tuple[str, ...]
    executable: bool = False


@dataclass(frozen=True)
class RuntimeSpec:
    engine: str
    title: str
    critical: bool
    requirements: tuple[Requirement, ...]


def _unit_paths(name: str) -> tuple[str, ...]:
    return (
        f"/etc/systemd/system/{name}",
        f"/usr/lib/systemd/system/{name}",
        f"/lib/systemd/system/{name}",
    )


DEFAULT_SPECS: dict[str, RuntimeSpec] = {
    "amneziawg": RuntimeSpec(
        "amneziawg",
        "AWG2",
        True,
        (
            Requirement("awg", ("/usr/bin/awg", "/usr/local/bin/awg"), True),
            Requirement("awg-quick", ("/usr/bin/awg-quick", "/usr/local/bin/awg-quick"), True),
            Requirement("sg-gateway-awg.service", _unit_paths("sg-gateway-awg.service")),
        ),
    ),
    "amneziawg3": RuntimeSpec(
        "amneziawg3",
        "AWG3",
        True,
        (
            Requirement("awg", ("/opt/sg-gateway/awg3/bin/awg",), True),
            Requirement("awg-quick", ("/opt/sg-gateway/awg3/bin/awg-quick",), True),
            Requirement("amneziawg-go", ("/opt/sg-gateway/awg3/bin/amneziawg-go",), True),
            Requirement(
                "AWG3 helper",
                ("/opt/sg-gateway/deploy/sg-gateway-awg3-userspace.sh",),
                True,
            ),
            Requirement("sg-gateway-awg3.service", _unit_paths("sg-gateway-awg3.service")),
        ),
    ),
    "xray": RuntimeSpec(
        "xray",
        "Xray",
        True,
        (
            Requirement("xray", ("/usr/local/bin/xray", "/usr/bin/xray"), True),
            Requirement("xray.service", _unit_paths("xray.service")),
        ),
    ),
    "mihomo": RuntimeSpec(
        "mihomo",
        "Mihomo / Mieru",
        False,
        (
            Requirement("mihomo", ("/usr/local/bin/mihomo", "/usr/bin/mihomo"), True),
            Requirement("mihomo.service", _unit_paths("mihomo.service")),
        ),
    ),
    "anytls": RuntimeSpec(
        "anytls",
        "sing-box / AnyTLS",
        False,
        (
            Requirement("sing-box", ("/usr/local/bin/sing-box", "/usr/bin/sing-box"), True),
            Requirement("sg-gateway-singbox.service", _unit_paths("sg-gateway-singbox.service")),
        ),
    ),
    "tuic": RuntimeSpec(
        "tuic",
        "sing-box / TUIC",
        False,
        (
            Requirement("sing-box", ("/usr/local/bin/sing-box", "/usr/bin/sing-box"), True),
            Requirement("sg-gateway-singbox.service", _unit_paths("sg-gateway-singbox.service")),
        ),
    ),
}

ENGINE_ALIASES = {
    "mieru": "mihomo",
}


def _active_engines(database_path: Path) -> set[str]:
    if not database_path.is_file():
        raise RuntimeContractError(f"Runtime Contract: база не найдена: {database_path}")

    database = sqlite3.connect(f"file:{database_path.as_posix()}?mode=ro", uri=True, timeout=15)
    try:
        try:
            rows = database.execute(
                """
                SELECT DISTINCT dc.engine
                FROM device_credentials dc
                JOIN devices d ON d.id = dc.device_id
                JOIN clients c ON c.id = d.client_id
                WHERE dc.status != 'disabled'
                  AND c.enabled = 1
                  AND d.enabled = 1
                """
            ).fetchall()
        except sqlite3.Error:
            rows = database.execute(
                "SELECT DISTINCT engine FROM device_credentials WHERE engine IS NOT NULL"
            ).fetchall()
    except sqlite3.Error as exc:
        raise RuntimeContractError(f"Runtime Contract: не удалось прочитать список движков: {exc}") from exc
    finally:
        database.close()

    result: set[str] = set()
    for row in rows:
        raw = str(row[0] or "").strip().lower()
        if raw:
            result.add(ENGINE_ALIASES.get(raw, raw))
    return result


def _requirement_ready(requirement: Requirement) -> tuple[bool, str]:
    for raw in requirement.alternatives:
        path = Path(raw)
        if not path.is_file():
            continue
        if requirement.executable and not os.access(path, os.X_OK):
            continue
        return True, str(path)
    return False, requirement.alternatives[0]


def inspect_runtime_contract(
    *,
    database_path: Path | str = "/var/lib/sg-gateway/sg-gateway.sqlite",
    strict_optional: bool = False,
    include_all_critical: bool = False,
    specs: Mapping[str, RuntimeSpec] | None = None,
) -> dict:
    selected_specs = dict(specs or DEFAULT_SPECS)
    active = _active_engines(Path(database_path))
    target_engines = {engine for engine in active if engine in selected_specs}
    if include_all_critical:
        target_engines.update(
            engine for engine, spec in selected_specs.items() if spec.critical
        )

    checks: list[dict] = []
    failures: list[dict] = []
    warnings: list[dict] = []
    for engine in sorted(target_engines):
        spec = selected_specs[engine]
        missing: list[str] = []
        resolved: dict[str, str] = {}
        for requirement in spec.requirements:
            ready, detail = _requirement_ready(requirement)
            if ready:
                resolved[requirement.label] = detail
            else:
                missing.append(f"{requirement.label}: {detail}")

        item = {
            "engine": engine,
            "title": spec.title,
            "critical": spec.critical,
            "active": engine in active,
            "ready": not missing,
            "missing": missing,
            "resolved": resolved,
        }
        checks.append(item)
        if missing:
            if spec.critical or strict_optional:
                failures.append(item)
            else:
                warnings.append(item)

    if failures:
        parts: list[str] = []
        for item in failures:
            missing = ", ".join(item["missing"])
            if item["engine"] == "amneziawg3":
                parts.append(f"AWG3 требует восстановления — отсутствует {missing}")
            else:
                parts.append(f"{item['title']} не готов — отсутствует {missing}")
        message = (
            "Runtime Contract не пройден. Настройки и клиенты не изменены. "
            + "; ".join(parts)
        )
    else:
        message = "Runtime Contract: обязательные runtime-компоненты готовы"

    return {
        "ok": not failures,
        "message": message,
        "active_engines": sorted(active),
        "checks": checks,
        "failures": failures,
        "warnings": warnings,
        "strict_optional": strict_optional,
        "include_all_critical": include_all_critical,
    }


def assert_runtime_contract(**kwargs) -> dict:
    result = inspect_runtime_contract(**kwargs)
    if not result.get("ok"):
        raise RuntimeContractError(str(result.get("message") or "Runtime Contract не пройден"))
    return result
'''
write("hostd/sg_hostd/runtime_contracts.py", RUNTIME_CONTRACTS)


DATA_BACKUP_RUNTIME = r'''from __future__ import annotations

import json
import os
import sqlite3
import tarfile
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from sg_hostd import full_backup_runtime as full
from sg_hostd.runtime_contracts import assert_runtime_contract


FORMAT = "sg-gateway-data-backup"
FORMAT_VERSION = 1
PREFIX = "SG-Gateway-DATA"
VERIFY_UPLOAD_NAME = "verify-upload.sgbackup"
VERIFIED_UPLOAD_NAME = "verified-upload.sgbackup"
RESTORE_UPLOAD_NAME = "restore-upload.sgbackup"
CANONICAL_CONFIG_DIR = Path("/etc/sg-gateway")
CANONICAL_DATA_DIR = Path("/var/lib/sg-gateway")
CANONICAL_LETSENCRYPT_DIR = Path("/etc/letsencrypt")


def _data_backup_dir() -> Path:
    root = full._data_dir() / "backups" / "data"
    root.mkdir(parents=True, exist_ok=True)
    os.chmod(root, 0o700)
    return root


def _work_dir() -> Path:
    root = full._data_dir() / "data-backup-work"
    root.mkdir(parents=True, exist_ok=True)
    os.chmod(root, 0o700)
    return root


def _archive_name(prefix: str = PREFIX) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-%f")
    return f"{prefix}-{stamp}.sgbackup"


def _add_path(tar: tarfile.TarFile, source: Path, arcname: str) -> None:
    tar.add(
        source,
        arcname=arcname,
        recursive=True,
        filter=full._portable_tar_filter,
    )


def create_data_backup_archive(
    prefix: str = PREFIX,
    *,
    source_data_dir: Path | None = None,
    source_config_dir: Path | None = None,
    source_letsencrypt_dir: Path | None = None,
    destination_dir: Path | None = None,
) -> dict:
    data_dir = Path(source_data_dir or full._data_dir())
    config_dir = Path(source_config_dir or CANONICAL_CONFIG_DIR)
    letsencrypt_dir = Path(source_letsencrypt_dir or CANONICAL_LETSENCRYPT_DIR)
    output_dir = Path(destination_dir or _data_backup_dir())
    output_dir.mkdir(parents=True, exist_ok=True)

    destination = output_dir / _archive_name(prefix)
    temporary = destination.with_name(f".{destination.name}.tmp")
    temporary.unlink(missing_ok=True)

    with tempfile.TemporaryDirectory(prefix="create-", dir=_work_dir() if destination_dir is None else None) as temp_name:
        temp = Path(temp_name)
        db_snapshot = temp / "sg-gateway.sqlite"
        full._sqlite_snapshot(data_dir / "sg-gateway.sqlite", db_snapshot)

        roots: list[tuple[Path, Path]] = []
        if config_dir.exists() or config_dir.is_symlink():
            roots.append((config_dir, CANONICAL_CONFIG_DIR))
        if letsencrypt_dir.exists() or letsencrypt_dir.is_symlink():
            roots.append((letsencrypt_dir, CANONICAL_LETSENCRYPT_DIR))

        data_roots: list[tuple[Path, Path]] = []
        for name in ("security", "warp"):
            source = data_dir / name
            if source.exists() or source.is_symlink():
                data_roots.append((source, CANONICAL_DATA_DIR / name))

        certificate_domains: list[str] = []
        live = letsencrypt_dir / "live"
        if live.is_dir():
            for item in sorted(live.iterdir()):
                if item.is_dir() and (item / "fullchain.pem").is_file() and (item / "privkey.pem").is_file():
                    certificate_domains.append(item.name)

        components = [str(canonical) for _, canonical in roots]
        components.extend(str(canonical) for _, canonical in data_roots)
        components.append(str(CANONICAL_DATA_DIR / "sg-gateway.sqlite"))
        manifest = {
            "format": FORMAT,
            "format_version": FORMAT_VERSION,
            "profile": "clients-and-settings",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "source_version": full._version(),
            "contains_private_keys": True,
            "contains_letsencrypt": letsencrypt_dir.exists(),
            "contains_letsencrypt_certificates": bool(certificate_domains),
            "certificate_domains": certificate_domains,
            "portable_restore": "destination public IP is preserved",
            "runtime_policy": "generated runtime is not archived; destination rebuilds it",
            "excluded": [
                "runtime binaries",
                "generated Xray/AWG/Mihomo/sing-box configs",
                "GeoIP cache",
                "backup history",
                "operation jobs",
            ],
            "components": components,
        }
        manifest_path = temp / "manifest.json"
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

        with tarfile.open(temporary, "w:gz", dereference=False) as tar:
            tar.add(manifest_path, arcname="manifest.json", recursive=False)
            tar.add(
                db_snapshot,
                arcname=f"payload/{CANONICAL_DATA_DIR.relative_to('/')}/sg-gateway.sqlite",
                recursive=False,
            )
            for source, canonical in roots:
                _add_path(tar, source, f"payload/{canonical.relative_to('/')}")
            for source, canonical in data_roots:
                _add_path(tar, source, f"payload/{canonical.relative_to('/')}")

    os.replace(temporary, destination)
    os.chmod(destination, 0o600)
    if os.geteuid() == 0:
        uid, gid = full._panel_ids()
        os.chown(destination, uid, gid)
    return {
        "name": destination.name,
        "path": str(destination),
        "size_bytes": destination.stat().st_size,
        "sha256": full._sha256(destination),
        "source_version": full._version(),
        "certificates": bool(certificate_domains),
        "certificate_domains": certificate_domains,
        "profile": "clients-and-settings",
    }


def _read_manifest(path: Path) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("format") != FORMAT or int(payload.get("format_version") or 0) != FORMAT_VERSION:
        raise RuntimeError("Unsupported SG-Gateway DATA backup format")
    return payload


def _extract_archive(archive: Path, target: Path) -> dict:
    with tarfile.open(archive, "r:gz") as tar:
        members = [member for member in tar.getmembers() if not full._is_internal_history_member(member.name)]
        full._validate_members(tar, target, members)
        tar.extractall(target, members=members)
    manifest = target / "manifest.json"
    if not manifest.is_file():
        raise RuntimeError("manifest.json is missing")
    return _read_manifest(manifest)


def _verify_database(db_path: Path) -> tuple[int, int]:
    if not db_path.is_file():
        raise RuntimeError("Backup does not contain the SG-Gateway database")
    database_size = db_path.stat().st_size
    database = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True, timeout=15)
    try:
        row = database.execute("PRAGMA integrity_check").fetchone()
        if not row or str(row[0]).lower() != "ok":
            raise RuntimeError("Uploaded SQLite database is damaged")
        table_count = int(
            database.execute(
                "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            ).fetchone()[0]
        )
    finally:
        database.close()
    if table_count <= 0:
        raise RuntimeError("SG-Gateway database contains no application tables")
    return database_size, table_count


def _verify_archive(archive: Path) -> dict:
    with tempfile.TemporaryDirectory(prefix="verify-data-", dir=_work_dir()) as temp_name:
        temp = Path(temp_name)
        manifest = _extract_archive(archive, temp)
        db_path = temp / "payload" / CANONICAL_DATA_DIR.relative_to("/") / "sg-gateway.sqlite"
        database_size, table_count = _verify_database(db_path)
        return {
            "verified": True,
            "format": FORMAT,
            "format_version": FORMAT_VERSION,
            "profile": "clients-and-settings",
            "source_version": str(manifest.get("source_version") or "unknown"),
            "created_at": str(manifest.get("created_at") or ""),
            "size_bytes": archive.stat().st_size,
            "sha256": full._sha256(archive),
            "database_size_bytes": database_size,
            "database_tables": table_count,
            "contains_letsencrypt": bool(manifest.get("contains_letsencrypt")),
            "contains_letsencrypt_certificates": bool(manifest.get("contains_letsencrypt_certificates")),
            "certificate_domains": list(manifest.get("certificate_domains") or []),
            "components": len(list(manifest.get("components") or [])),
            "checks": {
                "gzip_tar": "ok",
                "safe_paths": "ok",
                "manifest": "ok",
                "sqlite_integrity": "ok",
            },
        }


def verify_uploaded_data_backup() -> dict:
    directory = _data_backup_dir()
    archive = directory / VERIFY_UPLOAD_NAME
    verified = directory / VERIFIED_UPLOAD_NAME
    if not archive.is_file():
        raise RuntimeError("Uploaded DATA .sgbackup file for verification not found")
    verified.unlink(missing_ok=True)
    try:
        payload = _verify_archive(archive)
        archive.replace(verified)
        return payload
    finally:
        archive.unlink(missing_ok=True)


def promote_uploaded_data_backup() -> dict:
    directory = _data_backup_dir()
    archive = directory / RESTORE_UPLOAD_NAME
    if not archive.is_file():
        raise RuntimeError("Uploaded DATA .sgbackup file for restore not found")

    with tempfile.TemporaryDirectory(prefix="promote-data-", dir=_work_dir()) as temp_name:
        temp = Path(temp_name)
        manifest = _extract_archive(archive, temp)
        payload_root = temp / "payload"
        db_path = payload_root / CANONICAL_DATA_DIR.relative_to("/") / "sg-gateway.sqlite"
        _verify_database(db_path)
        contract = assert_runtime_contract(
            database_path=db_path,
            strict_optional=True,
            include_all_critical=True,
        )

        full._ensure_dirs()
        destination = full._backup_dir() / full.RESTORE_UPLOAD_NAME
        temporary = destination.with_name(f".{destination.name}.data-promote.tmp")
        destination.unlink(missing_ok=True)
        temporary.unlink(missing_ok=True)

        full_manifest = {
            "format": full.FORMAT,
            "format_version": full.FORMAT_VERSION,
            "created_at": str(manifest.get("created_at") or datetime.now(timezone.utc).isoformat()),
            "source_version": str(manifest.get("source_version") or "unknown"),
            "contains_private_keys": True,
            "contains_letsencrypt": bool(manifest.get("contains_letsencrypt")),
            "contains_letsencrypt_certificates": bool(manifest.get("contains_letsencrypt_certificates")),
            "certificate_domains": list(manifest.get("certificate_domains") or []),
            "portable_restore": "destination public IP is preserved",
            "excluded_history": ["security/backups", "security/jobs"],
            "components": list(manifest.get("components") or []),
            "data_profile": True,
            "promoted_from": FORMAT,
        }
        manifest_path = temp / "promoted-full-manifest.json"
        manifest_path.write_text(json.dumps(full_manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        with tarfile.open(temporary, "w:gz", dereference=False) as tar:
            tar.add(manifest_path, arcname="manifest.json", recursive=False)
            tar.add(payload_root, arcname="payload", recursive=True, filter=full._portable_tar_filter)

        os.replace(temporary, destination)
        os.chmod(destination, 0o600)
        archive.unlink(missing_ok=True)
        return {
            "promoted": True,
            "source_version": str(manifest.get("source_version") or "unknown"),
            "runtime_contract": contract,
            "full_restore_upload": str(destination),
        }
'''
write("hostd/sg_hostd/data_backup_runtime.py", DATA_BACKUP_RUNTIME)


replace_once(
    "hostd/sg_hostd/client_runtime.py",
    "        _repair_deployment_configs()\n\n        from sg_hostd.awg3_runtime import apply_awg3\n",
    "        # SG_GATEWAY_02206_RUNTIME_CONTRACT_V1\n        # Check active critical runtimes before the first engine mutates live state.\n        from sg_hostd.runtime_contracts import assert_runtime_contract\n\n        assert_runtime_contract(\n            database_path=DATA_DIR / \"sg-gateway.sqlite\",\n            strict_optional=False,\n            include_all_critical=False,\n        )\n        _repair_deployment_configs()\n\n        from sg_hostd.awg3_runtime import apply_awg3\n",
    marker="SG_GATEWAY_02206_RUNTIME_CONTRACT_V1",
)


replace_once(
    "hostd/sg_hostd/awg3_runtime.py",
    '''def apply_awg3() -> cr.EngineResult:\n    _tool(AWG3_AWG)\n    _tool(AWG3_AWG_QUICK)\n    _tool(AWG3_GO)\n    if not AWG3_HELPER.is_file():\n        raise cr.ClientRuntimeError(f"AWG3 runtime helper missing: {AWG3_HELPER}")\n    secrets = _ensure_server_secrets()\n    _repair_configs(secrets)\n    rows = cr._deployment_rows(ENGINE)\n    ids = [int(row["client_id"]) for row in rows]\n    previous = cr._status_snapshot(ENGINE)\n\n    if not rows:\n        subprocess.run(["systemctl", "stop", AWG3_SERVICE], capture_output=True, text=True, timeout=60, check=False)\n        return cr.EngineResult(ENGINE, True, "Нет активных клиентов AWG3", 0)\n\n''',
    '''def apply_awg3() -> cr.EngineResult:\n    # SG_GATEWAY_02206_AWG3_EMPTY_RUNTIME_V1\n    # Removing/disabling the last AWG3 client must remain possible even when an\n    # old installation never received the AWG3 userspace runtime. Only an\n    # active AWG3 deployment requires the tools.\n    rows = cr._deployment_rows(ENGINE)\n    ids = [int(row["client_id"]) for row in rows]\n    previous = cr._status_snapshot(ENGINE)\n\n    if not rows:\n        subprocess.run(["systemctl", "stop", AWG3_SERVICE], capture_output=True, text=True, timeout=60, check=False)\n        return cr.EngineResult(ENGINE, True, "Нет активных клиентов AWG3", 0)\n\n    _tool(AWG3_AWG)\n    _tool(AWG3_AWG_QUICK)\n    _tool(AWG3_GO)\n    if not AWG3_HELPER.is_file():\n        raise cr.ClientRuntimeError(f"AWG3 runtime helper missing: {AWG3_HELPER}")\n    secrets = _ensure_server_secrets()\n    _repair_configs(secrets)\n\n''',
    marker="SG_GATEWAY_02206_AWG3_EMPTY_RUNTIME_V1",
)


replace_once(
    "hostd/sg_hostd/full_backup_runtime.py",
    '''        _restore_progress("[Restore 2/7] Backup и SQLite проверены")\n        _restore_progress("[Restore 3/7] Создаю страховочный полный backup текущего сервера")\n''',
    '''        # SG_GATEWAY_02206_RESTORE_RUNTIME_CONTRACT_V1\n        # A portable restore must never touch the live server when the clean\n        # destination installation is already missing a required runtime.\n        from sg_hostd.runtime_contracts import assert_runtime_contract\n\n        assert_runtime_contract(\n            database_path=db_path,\n            strict_optional=True,\n            include_all_critical=True,\n        )\n        _restore_progress("[Restore 2/7] Backup, SQLite и Runtime Contract проверены")\n        _restore_progress("[Restore 3/7] Создаю страховочный полный backup текущего сервера")\n''',
    marker="SG_GATEWAY_02206_RESTORE_RUNTIME_CONTRACT_V1",
)


replace_once(
    "hostd/sg_hostd/commands.py",
    "from sg_hostd.full_backup_runtime import create_full_backup_archive, restore_uploaded_full_backup\n",
    "from sg_hostd.full_backup_runtime import create_full_backup_archive, restore_uploaded_full_backup\nfrom sg_hostd.data_backup_runtime import (\n    create_data_backup_archive,\n    promote_uploaded_data_backup,\n    verify_uploaded_data_backup,\n)\nfrom sg_hostd.runtime_contracts import inspect_runtime_contract\n",
    marker="from sg_hostd.data_backup_runtime import",
)

replace_once(
    "hostd/sg_hostd/commands.py",
    '''def _full_backup_create() -> HostCommandResult:\n''',
    '''# SG_GATEWAY_02206_DATA_BACKUP_COMMANDS_V1\ndef _runtime_contract_status() -> HostCommandResult:\n    try:\n        payload = inspect_runtime_contract(\n            strict_optional=False,\n            include_all_critical=True,\n        )\n    except Exception as exc:\n        return HostCommandResult(\n            command="runtime.contract", status="error",\n            message=f"Runtime Contract не выполнен: {exc}", payload={},\n        )\n    return HostCommandResult(\n        command="runtime.contract",\n        status="ok" if payload.get("ok") else "error",\n        message=str(payload.get("message") or "Runtime Contract"),\n        payload=payload,\n    )\n\n\ndef _data_backup_create() -> HostCommandResult:\n    try:\n        payload = create_data_backup_archive()\n    except Exception as exc:\n        return HostCommandResult(\n            command="backup.data.create", status="error",\n            message=f"Не удалось создать backup клиентов и настроек: {exc}", payload={},\n        )\n    return HostCommandResult(\n        command="backup.data.create", status="ok",\n        message=f"Backup клиентов и настроек создан: {payload.get('name', '')}", payload=payload,\n    )\n\n\ndef _data_backup_verify() -> HostCommandResult:\n    try:\n        payload = verify_uploaded_data_backup()\n    except Exception as exc:\n        return HostCommandResult(\n            command="backup.data.verify", status="error",\n            message=f"DATA backup не прошёл проверку: {exc}", payload={},\n        )\n    return HostCommandResult(\n        command="backup.data.verify", status="ok",\n        message="DATA backup проверен", payload=payload,\n    )\n\n\ndef _data_backup_promote() -> HostCommandResult:\n    try:\n        payload = promote_uploaded_data_backup()\n    except Exception as exc:\n        return HostCommandResult(\n            command="backup.data.promote", status="error",\n            message=f"DATA restore не подготовлен: {exc}", payload={},\n        )\n    return HostCommandResult(\n        command="backup.data.promote", status="ok",\n        message="DATA backup проверен Runtime Contract и подготовлен к переносимому restore",\n        payload=payload,\n    )\n\n\ndef _full_backup_create() -> HostCommandResult:\n''',
    marker="SG_GATEWAY_02206_DATA_BACKUP_COMMANDS_V1",
)

replace_once(
    "hostd/sg_hostd/commands.py",
    '''    "system.diagnostics": _system_diagnostics,\n    "backup.full.create": _full_backup_create,\n''',
    '''    "system.diagnostics": _system_diagnostics,\n    "runtime.contract": _runtime_contract_status,\n    "backup.data.create": _data_backup_create,\n    "backup.data.verify": _data_backup_verify,\n    "backup.data.promote": _data_backup_promote,\n    "backup.full.create": _full_backup_create,\n''',
    marker='"backup.data.create": _data_backup_create',
)


DATA_APP_BLOCK = r'''

# SG_GATEWAY_02206_DATA_BACKUP_PROFILE_V1
DATA_BACKUP_SUFFIX = ".sgbackup"
DATA_VERIFY_UPLOAD_NAME = "verify-upload.sgbackup"
DATA_VERIFIED_UPLOAD_NAME = "verified-upload.sgbackup"
DATA_RESTORE_UPLOAD_NAME = "restore-upload.sgbackup"
DATA_VERIFIED_METADATA_NAME = "verified-upload.json"
_DATA_TRANSIENT_UPLOAD_NAMES = {
    DATA_VERIFY_UPLOAD_NAME,
    DATA_VERIFIED_UPLOAD_NAME,
    DATA_RESTORE_UPLOAD_NAME,
}


def get_data_backup_dir() -> Path:
    directory = load_config().data_dir / "backups" / "data"
    directory.mkdir(parents=True, exist_ok=True)
    os.chmod(directory, 0o700)
    return directory


def list_data_backups() -> list[FullBackupInfo]:
    directory = get_data_backup_dir()
    paths = [
        path
        for path in directory.glob("SG-Gateway-DATA-*.sgbackup")
        if path.is_file() and path.name not in _DATA_TRANSIENT_UPLOAD_NAMES
    ]
    return sorted((_info(path) for path in paths), key=lambda item: item.name, reverse=True)


def get_data_backup(name: str) -> FullBackupInfo | None:
    if not _valid_name(name) or not name.startswith("SG-Gateway-DATA-"):
        return None
    path = get_data_backup_dir() / name
    if not path.is_file() or path.name in _DATA_TRANSIENT_UPLOAD_NAMES:
        return None
    return _info(path)


def clear_verified_data_backup() -> None:
    directory = get_data_backup_dir()
    (directory / DATA_VERIFIED_UPLOAD_NAME).unlink(missing_ok=True)
    (directory / DATA_VERIFIED_METADATA_NAME).unlink(missing_ok=True)


def stage_uploaded_data_backup_for_verification(file_storage) -> Path:
    clear_verified_data_backup()
    original = str(getattr(file_storage, "filename", "") or "").strip()
    if not original.lower().endswith(DATA_BACKUP_SUFFIX):
        raise ValueError("Нужен файл SG-Gateway с расширением .sgbackup")

    directory = get_data_backup_dir()
    destination = directory / DATA_VERIFY_UPLOAD_NAME
    temporary = directory / f".{DATA_VERIFY_UPLOAD_NAME}.tmp"
    temporary.unlink(missing_ok=True)
    total = 0
    with temporary.open("wb") as handle:
        while True:
            chunk = file_storage.stream.read(1024 * 1024)
            if not chunk:
                break
            total += len(chunk)
            handle.write(chunk)
        handle.flush()
        os.fsync(handle.fileno())
    if total < 128:
        temporary.unlink(missing_ok=True)
        raise ValueError("Файл backup пустой или повреждён")
    os.chmod(temporary, 0o600)
    os.replace(temporary, destination)
    return destination


def save_verified_data_backup(original_name: str, payload: dict) -> dict:
    directory = get_data_backup_dir()
    archive = directory / DATA_VERIFIED_UPLOAD_NAME
    if not archive.is_file():
        raise RuntimeError("Проверенный DATA backup не найден")
    expected_sha256 = str(payload.get("sha256") or "").strip().lower()
    actual_sha256 = _sha256(archive)
    if not expected_sha256 or actual_sha256 != expected_sha256:
        clear_verified_data_backup()
        raise RuntimeError("SHA-256 проверенного DATA backup не совпал")
    metadata = {
        "original_name": str(original_name or DATA_VERIFIED_UPLOAD_NAME),
        "size_bytes": archive.stat().st_size,
        "sha256": actual_sha256,
        "source_version": str(payload.get("source_version") or "unknown"),
        "created_at": str(payload.get("created_at") or "не указано"),
        "database_tables": int(payload.get("database_tables") or 0),
        "database_size_bytes": int(payload.get("database_size_bytes") or 0),
        "contains_letsencrypt_certificates": bool(payload.get("contains_letsencrypt_certificates")),
        "profile": "clients-and-settings",
    }
    destination = directory / DATA_VERIFIED_METADATA_NAME
    temporary = directory / f".{DATA_VERIFIED_METADATA_NAME}.tmp"
    temporary.unlink(missing_ok=True)
    with temporary.open("w", encoding="utf-8") as handle:
        json.dump(metadata, handle, ensure_ascii=False, sort_keys=True)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.chmod(temporary, 0o600)
    os.replace(temporary, destination)
    return metadata


def get_verified_data_backup() -> dict | None:
    directory = get_data_backup_dir()
    archive = directory / DATA_VERIFIED_UPLOAD_NAME
    metadata_path = directory / DATA_VERIFIED_METADATA_NAME
    if not archive.is_file() or not metadata_path.is_file():
        return None
    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        if not isinstance(metadata, dict):
            return None
        if int(metadata.get("size_bytes") or -1) != archive.stat().st_size:
            return None
        if len(str(metadata.get("sha256") or "")) != 64:
            return None
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return None
    return metadata


def stage_verified_data_backup_for_restore() -> dict:
    metadata = get_verified_data_backup()
    if metadata is None:
        raise RuntimeError("Сначала выберите и проверьте DATA .sgbackup")
    directory = get_data_backup_dir()
    archive = directory / DATA_VERIFIED_UPLOAD_NAME
    actual_sha256 = _sha256(archive)
    if actual_sha256 != str(metadata.get("sha256") or ""):
        clear_verified_data_backup()
        raise RuntimeError("Проверенный DATA backup изменился: выберите файл заново")
    os.replace(archive, directory / DATA_RESTORE_UPLOAD_NAME)
    (directory / DATA_VERIFIED_METADATA_NAME).unlink(missing_ok=True)
    return metadata
'''
full_backups_path = "app/maintenance/full_backups.py"
full_backups_body = read(full_backups_path)
if "SG_GATEWAY_02206_DATA_BACKUP_PROFILE_V1" not in full_backups_body:
    write(full_backups_path, full_backups_body.rstrip() + "\n" + DATA_APP_BLOCK.lstrip())


replace_once(
    "app/main.py",
    '''from app.maintenance.full_backups import (\n    get_full_backup,\n    get_verified_full_backup,\n    list_full_backups,\n    save_verified_full_backup,\n    stage_uploaded_full_backup_for_verification,\n    stage_verified_full_backup_for_restore,\n)\n''',
    '''from app.maintenance.full_backups import (\n    get_data_backup,\n    get_full_backup,\n    get_verified_data_backup,\n    get_verified_full_backup,\n    list_data_backups,\n    list_full_backups,\n    save_verified_data_backup,\n    save_verified_full_backup,\n    stage_uploaded_data_backup_for_verification,\n    stage_uploaded_full_backup_for_verification,\n    stage_verified_data_backup_for_restore,\n    stage_verified_full_backup_for_restore,\n)\n''',
    marker="get_verified_data_backup",
)

replace_once(
    "app/main.py",
    '''            backup_cleanup=backup_cleanup_preview(backups),\n            full_backups=list_full_backups(),\n            verified_full_backup=get_verified_full_backup(),\n''',
    '''            backup_cleanup=backup_cleanup_preview(backups),\n            data_backups=list_data_backups(),\n            verified_data_backup=get_verified_data_backup(),\n            full_backups=list_full_backups(),\n            verified_full_backup=get_verified_full_backup(),\n''',
    marker="data_backups=list_data_backups()",
)

DATA_ROUTES = r'''    # SG_GATEWAY_02206_DATA_BACKUP_ROUTES_V1
    @app.post("/maintenance/data-backups")
    def create_data_backup_route():
        result = run_hostd_command("backup.data.create", timeout=180)
        if result.status != "ok":
            flash(result.message or "Не удалось создать backup клиентов и настроек", "error")
            return redirect(url_for("maintenance", tab="backups"))
        name = str(result.payload.get("name") or "")
        flash(f"Backup клиентов и настроек создан: {name}", "success")
        return redirect(url_for("maintenance", tab="backups"))

    @app.get("/maintenance/data-backups/<name>/download")
    def download_data_backup_route(name: str):
        backup = get_data_backup(name)
        if backup is None:
            abort(404)
        return send_file(
            backup.path, as_attachment=True, download_name=backup.name,
            mimetype="application/octet-stream",
        )

    @app.post("/maintenance/data-backups/restore")
    def restore_data_backup_route():
        backup_action = request.form.get("backup_action", "").strip().lower()
        if backup_action == "restore_verified":
            try:
                stage_verified_data_backup_for_restore()
            except (OSError, RuntimeError, ValueError) as exc:
                flash(str(exc), "error")
                return redirect(url_for("maintenance", tab="backups"))

            promoted = run_hostd_command("backup.data.promote", timeout=180)
            if promoted.status != "ok":
                flash(promoted.message or "DATA restore не подготовлен", "error")
                return redirect(url_for("maintenance", tab="backups"))

            result = run_hostd_command("backup.full.restore.start", timeout=20)
            if result.status != "ok":
                flash(result.message or "DATA restore не запущен", "error")
                return redirect(url_for("maintenance", tab="backups"))
            return redirect(
                url_for(
                    "operation_job",
                    job_id=str(result.payload.get("job_id") or ""),
                )
            )

        if backup_action != "verify":
            flash("Сначала выберите и проверьте DATA .sgbackup", "error")
            return redirect(url_for("maintenance", tab="backups"))

        upload = request.files.get("backup")
        original_name = str(getattr(upload, "filename", "") or "").strip() if upload is not None else ""
        if upload is None or not original_name:
            flash("Выберите DATA .sgbackup", "error")
            return redirect(url_for("maintenance", tab="backups"))

        try:
            stage_uploaded_data_backup_for_verification(upload)
        except ValueError as exc:
            log_operation("backup.data.verify", f"backup:{original_name}", str(exc), status="error")
            flash(str(exc), "error")
            return redirect(url_for("maintenance", tab="backups"))

        try:
            result = run_hostd_command("backup.data.verify", timeout=180)
        except Exception as exc:
            message = f"Проверка DATA backup не выполнена: {exc}"
            log_operation("backup.data.verify", f"backup:{original_name}", message, status="error")
            flash(message, "error")
            return redirect(url_for("maintenance", tab="backups"))

        if result.status != "ok":
            message = result.message or "DATA backup не прошёл проверку"
            log_operation("backup.data.verify", f"backup:{original_name}", message, status="error")
            flash(f"DATA backup НЕ прошёл проверку: {message}", "error")
            return redirect(url_for("maintenance", tab="backups"))

        payload = result.payload or {}
        try:
            save_verified_data_backup(original_name, payload)
        except (OSError, RuntimeError, ValueError) as exc:
            message = f"DATA backup проверен, но не подготовлен к восстановлению: {exc}"
            log_operation("backup.data.verify", f"backup:{original_name}", message, status="error")
            flash(message, "error")
            return redirect(url_for("maintenance", tab="backups"))

        source_version = str(payload.get("source_version") or "unknown")
        tables = int(payload.get("database_tables") or 0)
        database_size = _format_bytes(payload.get("database_size_bytes") or 0)
        certificates = "есть" if payload.get("contains_letsencrypt_certificates") else "нет"
        message = (
            f"DATA backup исправен: {original_name}. SG-Gateway {source_version}; "
            f"SQLite: OK, таблиц {tables}, {database_size}; сертификаты: {certificates}. "
            "Перед восстановлением будет проверен Runtime Contract целевого сервера."
        )
        log_operation("backup.data.verify", f"backup:{original_name}", message)
        flash(message, "success")
        return redirect(url_for("maintenance", tab="backups"))

'''
replace_once(
    "app/main.py",
    '''    @app.post("/maintenance/full-backups")\n    def create_full_backup_route():\n''',
    DATA_ROUTES + '''    @app.post("/maintenance/full-backups")\n    def create_full_backup_route():\n''',
    marker="SG_GATEWAY_02206_DATA_BACKUP_ROUTES_V1",
)

replace_once(
    "app/web/templates/maintenance.html",
    "  'backup.full.verify': 'Проверен полный backup',\n",
    "  'backup.full.verify': 'Проверен полный backup',\n  'backup.data.verify': 'Проверен backup клиентов и настроек',\n",
    marker="'backup.data.verify':",
)

DATA_CARD = r'''  {# SG_GATEWAY_02206_DATA_BACKUP_CARD_V1 #}
  <article class="mtv2-panel sg-ljd-card-large sg-full-backup-card sg-data-backup-card">
    <header class="mtv2-panel-head sg-full-backup-head">
      <div>
        <div class="mtv2-card-kicker">CLIENTS & SETTINGS</div>
        <h2>Клиенты и настройки</h2>
        <p>Лёгкая переносимая копия: клиенты, устройства, ключи, Routing, WARP, HTTPS и сертификаты. Cores и сгенерированный runtime не архивируются.</p>
      </div>
      <form method="post" action="{{ url_for('create_data_backup_route') }}">
        <button class="button primary sg-full-create" type="submit">
          <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 3v12m0 0 4-4m-4 4-4-4M5 19h14"/></svg>
          <span>Создать DATA backup</span>
        </button>
      </form>
    </header>

    <div class="sg-full-backup-grid">
      <section class="sg-full-backup-note sg-ljd-nested">
        <div class="sg-full-section-title">
          <span class="sg-full-section-icon" aria-hidden="true"><svg viewBox="0 0 24 24"><path d="M4 7.5 12 3l8 4.5v9L12 21l-8-4.5zM4 7.5 12 12l8-4.5M12 12v9"/></svg></span>
          <div><strong>Что переносится</strong><small>Только source-of-truth пользователя. Runtime на новом сервере строится заново.</small></div>
        </div>
        <div class="sg-full-backup-components">
          <em>Клиенты</em><em>Устройства</em><em>Credentials</em><em>Routing</em><em>WARP</em><em>HTTPS</em><em>Сертификаты</em><em>Настройки</em>
        </div>
        <div class="sg-full-backup-detail">Ссылки и QR не копируются как картинки: после Restore SG-Gateway пересобирает их из той же базы и ключей.</div>
        <div class="sg-full-backup-warning">
          <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 3 3.5 19h17zM12 9v4m0 3h.01"/></svg>
          <span><strong>Без старого runtime.</strong> Xray/AWG/Mihomo/sing-box configs и binaries не переносятся — это защищает новый сервер от старого повреждённого состояния.</span>
        </div>
      </section>

      <section class="sg-full-restore-box sg-ljd-nested">
        <div class="sg-full-section-title">
          <span class="sg-full-section-icon restore" aria-hidden="true"><svg viewBox="0 0 24 24"><path d="M12 21V9m0 0 4 4m-4-4-4 4M5 5h14"/></svg></span>
          <div><strong>Восстановить клиентов и настройки</strong><small>До изменения данных проверяются архив, SQLite и Runtime Contract чистой установки.</small></div>
        </div>
        <form class="sg-full-upload" method="post" action="{{ url_for('restore_data_backup_route') }}" enctype="multipart/form-data"
              data-sg-full-upload
              data-sg-full-verified="{{ '1' if verified_data_backup else '0' }}"
              data-sg-verified-name="{{ verified_data_backup.original_name if verified_data_backup else '' }}"
              data-sg-verified-size="{{ verified_data_backup.size_bytes if verified_data_backup else '' }}"
              data-sg-confirm="Восстановить клиентов и настройки из проверенного файла? Перед изменением текущего сервера будет создан страховочный Full Backup."
              data-sg-confirm-title="Восстановить клиентов и настройки" data-sg-confirm-button="Восстановить" data-sg-confirm-tone="danger">
          <input class="sg-full-file-input" id="sg-data-backup-file" type="file" name="backup" accept=".sgbackup" data-sg-full-file>
          <label class="sg-full-file-picker" for="sg-data-backup-file">
            <span class="sg-full-file-icon" aria-hidden="true"><svg viewBox="0 0 24 24"><path d="M12 16V4m0 0 4 4m-4-4-4 4M5 15v4h14v-4"/></svg></span>
            <span class="sg-full-file-copy">
              <strong data-sg-full-file-name>Выберите DATA .sgbackup</strong>
              <small data-sg-full-file-meta>Нажмите, чтобы выбрать файл · размер не ограничен</small>
            </span>
            <span class="sg-full-file-action">Выбрать файл</span>
          </label>
          <div class="sg-full-restore-actions">
            <span class="sg-full-restore-note">Проверка ничего не меняет. Restore запускается только после Runtime Contract и использует страховочный Full Backup для автоматического rollback.</span>
            <button class="button sg-full-restore-button sg-full-verify-button" type="submit" name="backup_action" value="verify" disabled data-sg-full-verify-button>
              <svg viewBox="0 0 24 24" aria-hidden="true"><path d="m5 12 4 4L19 6"/></svg><span>Проверить DATA backup</span>
            </button>
            <button class="button mtv2-restore sg-full-restore-button" type="submit" name="backup_action" value="restore_verified" {% if not verified_data_backup %}disabled{% endif %} data-sg-full-restore-button>
              <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 12a8 8 0 1 0 2.3-5.7M4 4v6h6"/></svg><span>Восстановить данные</span>
            </button>
          </div>
        </form>
      </section>
    </div>

    {% if data_backups %}
      {% set data_backup = data_backups[0] %}
      <div class="sg-full-backup-latest sg-ljd-nested">
        <div class="sg-full-latest-main">
          <span class="sg-full-latest-icon" aria-hidden="true"><svg viewBox="0 0 24 24"><path d="M5 3h10l4 4v14H5zM14 3v5h5M8 13h8M8 17h5"/></svg></span>
          <div><span class="sg-full-latest-label">ПОСЛЕДНИЙ DATA BACKUP</span><strong>{{ data_backup.created_at }}</strong><small>{{ data_backup.name }} · <span data-bytes="{{ data_backup.size_bytes }}">{{ data_backup.size_bytes }} B</span></small></div>
        </div>
        <a class="button sg-full-download" href="{{ url_for('download_data_backup_route', name=data_backup.name) }}">
          <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 4v11m0 0 4-4m-4 4-4-4M5 20h14"/></svg><span>Скачать DATA .sgbackup</span>
        </a>
      </div>
    {% endif %}
  </article>

'''
replace_once(
    "app/web/templates/maintenance.html",
    '''  <article class="mtv2-panel sg-ljd-card-large sg-full-backup-card">\n''',
    DATA_CARD + '''  <article class="mtv2-panel sg-ljd-card-large sg-full-backup-card">\n''',
    marker="SG_GATEWAY_02206_DATA_BACKUP_CARD_V1",
)


TESTS = r'''from __future__ import annotations

import os
import sqlite3
import sys
import tarfile
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
HOSTD = ROOT / "hostd"
if str(HOSTD) not in sys.path:
    sys.path.insert(0, str(HOSTD))

from sg_hostd import data_backup_runtime, runtime_contracts


def _active_engine_db(path: Path, engine: str) -> None:
    con = sqlite3.connect(path)
    try:
        con.executescript(
            """
            CREATE TABLE clients (id INTEGER PRIMARY KEY, enabled INTEGER NOT NULL);
            CREATE TABLE devices (id INTEGER PRIMARY KEY, client_id INTEGER NOT NULL, enabled INTEGER NOT NULL);
            CREATE TABLE device_credentials (device_id INTEGER NOT NULL, engine TEXT NOT NULL, status TEXT NOT NULL);
            INSERT INTO clients(id, enabled) VALUES (1, 1);
            INSERT INTO devices(id, client_id, enabled) VALUES (1, 1, 1);
            """
        )
        con.execute(
            "INSERT INTO device_credentials(device_id, engine, status) VALUES (1, ?, 'applied')",
            (engine,),
        )
        con.commit()
    finally:
        con.close()


def test_runtime_contract_blocks_missing_awg3_before_apply(tmp_path: Path) -> None:
    db = tmp_path / "sg-gateway.sqlite"
    _active_engine_db(db, "amneziawg3")
    awg = tmp_path / "awg"
    awg_quick = tmp_path / "awg-quick"
    helper = tmp_path / "helper.sh"
    unit = tmp_path / "awg3.service"
    for path in (awg, awg_quick, helper, unit):
        path.write_text("x\n", encoding="utf-8")
    for path in (awg, awg_quick, helper):
        os.chmod(path, 0o755)
    missing_go = tmp_path / "amneziawg-go"

    specs = {
        "amneziawg3": runtime_contracts.RuntimeSpec(
            "amneziawg3",
            "AWG3",
            True,
            (
                runtime_contracts.Requirement("awg", (str(awg),), True),
                runtime_contracts.Requirement("awg-quick", (str(awg_quick),), True),
                runtime_contracts.Requirement("amneziawg-go", (str(missing_go),), True),
                runtime_contracts.Requirement("helper", (str(helper),), True),
                runtime_contracts.Requirement("unit", (str(unit),)),
            ),
        )
    }
    result = runtime_contracts.inspect_runtime_contract(database_path=db, specs=specs)
    assert result["ok"] is False
    assert "AWG3 требует восстановления" in result["message"]
    assert "Настройки и клиенты не изменены" in result["message"]

    missing_go.write_text("x\n", encoding="utf-8")
    os.chmod(missing_go, 0o755)
    result = runtime_contracts.inspect_runtime_contract(database_path=db, specs=specs)
    assert result["ok"] is True


def test_apply_contract_runs_before_engine_mutation_and_awg3_empty_is_safe() -> None:
    client_source = (ROOT / "hostd/sg_hostd/client_runtime.py").read_text(encoding="utf-8")
    apply_all = client_source.split("def apply_all_clients()", 1)[1]
    assert apply_all.index("assert_runtime_contract(") < apply_all.index("_repair_deployment_configs()")
    assert apply_all.index("assert_runtime_contract(") < apply_all.index("_apply_awg()")

    awg3_source = (ROOT / "hostd/sg_hostd/awg3_runtime.py").read_text(encoding="utf-8")
    apply_awg3 = awg3_source.split("def apply_awg3()", 1)[1]
    assert apply_awg3.index("if not rows:") < apply_awg3.index("_tool(AWG3_AWG)")


def test_full_restore_contract_is_before_safety_backup() -> None:
    source = (ROOT / "hostd/sg_hostd/full_backup_runtime.py").read_text(encoding="utf-8")
    restore = source.split("def restore_uploaded_full_backup()", 1)[1]
    assert restore.index("assert_runtime_contract(") < restore.index("create_full_backup_archive(prefix=\"SG-Gateway-SAFETY\")")


def test_data_backup_contains_only_portable_source_of_truth(tmp_path: Path) -> None:
    data = tmp_path / "data"
    config = tmp_path / "config"
    letsencrypt = tmp_path / "letsencrypt"
    output = tmp_path / "out"
    data.mkdir()
    config.mkdir()
    (data / "security").mkdir()
    (data / "security" / "backups").mkdir()
    (data / "security" / "jobs").mkdir()
    (data / "warp").mkdir()
    (data / "geoip").mkdir()
    letsencrypt.mkdir()

    db = data / "sg-gateway.sqlite"
    con = sqlite3.connect(db)
    try:
        con.execute("CREATE TABLE clients(id INTEGER PRIMARY KEY, enabled INTEGER)")
        con.execute("INSERT INTO clients(id, enabled) VALUES (1, 1)")
        con.commit()
    finally:
        con.close()

    (config / "engine-secrets.env").write_text("TEST=1\n", encoding="utf-8")
    (data / "security" / "tls-state.json").write_text("{}\n", encoding="utf-8")
    (data / "security" / "backups" / "old.db").write_text("no\n", encoding="utf-8")
    (data / "security" / "jobs" / "job.json").write_text("no\n", encoding="utf-8")
    (data / "warp" / "account.toml").write_text("test\n", encoding="utf-8")
    (data / "geoip" / "cache.dat").write_text("no\n", encoding="utf-8")

    created = data_backup_runtime.create_data_backup_archive(
        source_data_dir=data,
        source_config_dir=config,
        source_letsencrypt_dir=letsencrypt,
        destination_dir=output,
    )
    archive = Path(created["path"])
    with tarfile.open(archive, "r:gz") as tar:
        names = set(tar.getnames())
    assert "payload/var/lib/sg-gateway/sg-gateway.sqlite" in names
    assert "payload/etc/sg-gateway/engine-secrets.env" in names
    assert "payload/var/lib/sg-gateway/security/tls-state.json" in names
    assert "payload/var/lib/sg-gateway/warp/account.toml" in names
    assert not any("security/backups" in name for name in names)
    assert not any("security/jobs" in name for name in names)
    assert not any("/geoip" in name for name in names)
    assert not any("/usr/local/etc/xray" in name for name in names)
    assert not any("/etc/amnezia/amneziawg" in name for name in names)


def test_data_backup_ui_and_hostd_commands_are_wired() -> None:
    main = (ROOT / "app/main.py").read_text(encoding="utf-8")
    template = (ROOT / "app/web/templates/maintenance.html").read_text(encoding="utf-8")
    commands = (ROOT / "hostd/sg_hostd/commands.py").read_text(encoding="utf-8")
    assert '"/maintenance/data-backups"' in main
    assert '"/maintenance/data-backups/restore"' in main
    assert "backup.data.promote" in main
    assert "Клиенты и настройки" in template
    assert "Runtime Contract" in template
    assert '"runtime.contract": _runtime_contract_status' in commands
    assert '"backup.data.create": _data_backup_create' in commands
    assert '"backup.data.verify": _data_backup_verify' in commands
    assert '"backup.data.promote": _data_backup_promote' in commands
'''
write("tests/test_sg_gateway_v22_runtime_contract_data_backup.py", TESTS)

print("DEV 02206 runtime contract + DATA backup patch applied")
