from __future__ import annotations

import hashlib
import json
import os
import pwd
import re
import shlex
import grp
import shutil
import sqlite3
import subprocess
import tarfile
import tempfile
from datetime import datetime, timezone
from pathlib import Path


FORMAT = "sg-gateway-full-backup"
FORMAT_VERSION = 1
DEFAULT_DATA_DIR = Path("/var/lib/sg-gateway")
CONFIG_DIR = Path("/etc/sg-gateway")
BACKUP_DIR_NAME = Path("backups/full")
RESTORE_UPLOAD_NAME = "restore-upload.sgbackup"
PANEL_USER = "sg-gateway"
PANEL_GROUP = "sg-gateway"

# FULL_BACKUP_RESTORE_LIVE_TERMINAL_FIX4_1
def _restore_progress(message: str) -> None:
    print(message, flush=True)

# Full Backup keeps the live files for disaster recovery and audit.  Portable
# restore intentionally does NOT copy machine-generated runtime configs from
# the old VPS.  They are regenerated from the restored database + secrets on
# the destination machine.  This avoids stale interface/IP/runtime state.
ROOT_COMPONENTS = (
    CONFIG_DIR,
    Path("/etc/letsencrypt"),
    Path("/etc/amnezia/amneziawg"),
    Path("/etc/mihomo"),
    Path("/etc/sing-box"),
    Path("/usr/local/etc/xray"),
    Path("/usr/local/share/xray"),
    Path("/etc/nginx/sites-available/sg-gateway"),
    Path("/etc/nginx/stream-conf.d/sg-gateway-443.conf"),
)

# SG_GATEWAY_02111_PORTABLE_RESTORE_V2
# Only source-of-truth state is overlaid onto a fresh installation.
PORTABLE_STATE_ROOTS = (
    CONFIG_DIR,
    Path("/etc/letsencrypt"),
    Path("/usr/local/share/xray"),
)

GENERATED_RUNTIME_PATHS = (
    Path("/etc/amnezia/amneziawg/awg0.conf"),
    Path("/etc/mihomo/config.yaml"),
    Path("/etc/sing-box/config.json"),
    Path("/usr/local/etc/xray/config.json"),
    Path("/usr/local/etc/xray/tls"),
)

DATA_COMPONENTS = ("security", "warp", "geoip")

# SG_GATEWAY_02111_OPERATION_JOB_PRESERVE_FIX
# Operation jobs and local backup history are transient machine state. They must
# never be archived/restored because a rollback would overwrite the live job
# log/status that explains why the restore failed.
TRANSIENT_SECURITY_DIRS = {"backups", "jobs"}

# Values tied to the destination machine must survive a restore onto a new VPS.
# SG_GATEWAY_02111_RESTORE_SESSION_PRESERVE_FIX
# Keep the destination Flask signing key so the browser session remains valid
# across Full Restore + panel restart. Restoring the source VPS secret would
# invalidate the in-progress operation-job session and force a new login.
PRESERVE_SG_ENV = {
    "SG_GATEWAY_SECRET_KEY",
    "SG_GATEWAY_HOST",
    "SG_GATEWAY_PORT",
    "SG_GATEWAY_PUBLIC_PORT",
    "SG_GATEWAY_PUBLIC_ADDRESS",
    "SG_GATEWAY_DATA_DIR",
    "SG_GATEWAY_LOG_DIR",
    "SG_GATEWAY_HOSTD_URL",
    "SG_GATEWAY_SECURITY_STATE_DIR",
    "SG_GATEWAY_OPERATION_JOB_DIR",
}
PRESERVE_RUNTIME_ENV = {
    "SG_GATEWAY_PUBLIC_ADDRESS",
    "SG_GATEWAY_PANEL_PORT",
    "SG_GATEWAY_XRAY_REQUIRED_VERSION",
    "SG_GATEWAY_XRAY_MINIMUM_VERSION",
    "SG_GATEWAY_AWG_TOOLS_VERSION",
    "SG_GATEWAY_AWG_KMOD_VERSION",
    "SG_GATEWAY_MIHOMO_VERSION",
    "SG_GATEWAY_SINGBOX_VERSION",
    "SG_GATEWAY_WGCF_VERSION",
}


def _data_dir() -> Path:
    return Path(os.getenv("SG_GATEWAY_DATA_DIR", str(DEFAULT_DATA_DIR)))


def _backup_dir() -> Path:
    return _data_dir() / BACKUP_DIR_NAME


def _work_dir() -> Path:
    return _data_dir() / "full-backup-work"


def _ensure_dirs() -> None:
    backup_dir = _backup_dir()
    work_dir = _work_dir()
    backup_dir.mkdir(parents=True, exist_ok=True)
    work_dir.mkdir(parents=True, exist_ok=True)
    os.chmod(backup_dir, 0o700)
    uid, gid = _panel_ids()
    os.chown(backup_dir, uid, gid)
    os.chmod(work_dir, 0o700)


def _panel_ids() -> tuple[int, int]:
    try:
        uid = pwd.getpwnam(PANEL_USER).pw_uid
        gid = grp.getgrnam(PANEL_GROUP).gr_gid
        return uid, gid
    except KeyError:
        return 0, 0


def _set_download_permissions(path: Path) -> None:
    uid, gid = _panel_ids()
    os.chown(path, uid, gid)
    os.chmod(path, 0o600)


def _version() -> str:
    path = Path("/opt/sg-gateway/VERSION")
    try:
        return path.read_text(encoding="utf-8").strip() or "unknown"
    except OSError:
        return "unknown"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sqlite_snapshot(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if not source.is_file():
        raise RuntimeError(f"SQLite database not found: {source}")
    src = sqlite3.connect(f"file:{source}?mode=ro", uri=True, timeout=15)
    dst = sqlite3.connect(destination, timeout=15)
    try:
        src.backup(dst)
        row = dst.execute("PRAGMA integrity_check").fetchone()
        if not row or str(row[0]).lower() != "ok":
            raise RuntimeError("SQLite integrity_check failed")
    finally:
        dst.close()
        src.close()
    os.chmod(destination, 0o600)


def _letsencrypt_certificate_domains() -> list[str]:
    live = Path("/etc/letsencrypt/live")
    if not live.is_dir():
        return []
    domains: list[str] = []
    for item in sorted(live.iterdir()):
        if not item.is_dir():
            continue
        if (item / "fullchain.pem").is_file() and (item / "privkey.pem").is_file():
            domains.append(item.name)
    return domains


def _archive_sources() -> tuple[list[Path], list[Path]]:
    roots = [path for path in ROOT_COMPONENTS if path.exists() or path.is_symlink()]
    data = []
    base = _data_dir()
    for name in DATA_COMPONENTS:
        path = base / name
        if path.exists() or path.is_symlink():
            data.append(path)
    return roots, data


def _archive_name(prefix: str) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-%f")
    return f"{prefix}-{stamp}.sgbackup"


# FULL_BACKUP_EXCLUDE_INTERNAL_HISTORY_FIX2
# SG_GATEWAY_02111_OPERATION_JOB_PRESERVE_FIX
def _is_internal_history_member(name: str) -> bool:
    parts = Path(str(name or "").strip("/")).parts
    if not parts or parts[0] != "payload":
        return False
    return any(
        parts[index] == "security" and parts[index + 1] in TRANSIENT_SECURITY_DIRS
        for index in range(1, len(parts) - 1)
    )


def _portable_tar_filter(member: tarfile.TarInfo) -> tarfile.TarInfo | None:
    if _is_internal_history_member(member.name):
        return None
    return member


def _add_path(tar: tarfile.TarFile, source: Path, arcname: str) -> None:
    tar.add(
        source,
        arcname=arcname,
        recursive=True,
        filter=_portable_tar_filter,
    )


def create_full_backup_archive(prefix: str = "SG-Gateway-FULL") -> dict:
    _ensure_dirs()
    roots, data_paths = _archive_sources()
    destination = _backup_dir() / _archive_name(prefix)
    temporary = destination.with_name(f".{destination.name}.tmp")
    temporary.unlink(missing_ok=True)

    with tempfile.TemporaryDirectory(prefix="create-", dir=_work_dir()) as temp_name:
        temp = Path(temp_name)
        db_snapshot = temp / "sg-gateway.sqlite"
        _sqlite_snapshot(_data_dir() / "sg-gateway.sqlite", db_snapshot)

        components = [str(path) for path in roots]
        components.extend(str(path) for path in data_paths)
        components.append(str(_data_dir() / "sg-gateway.sqlite"))
        certificate_domains = _letsencrypt_certificate_domains()
        manifest = {
            "format": FORMAT,
            "format_version": FORMAT_VERSION,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "source_version": _version(),
            "contains_private_keys": True,
            "contains_letsencrypt": Path("/etc/letsencrypt").exists(),
            "contains_letsencrypt_certificates": bool(certificate_domains),
            "certificate_domains": certificate_domains,
            "portable_restore": "destination public IP is preserved",
            "excluded_history": ["security/backups", "security/jobs"],
            "components": components,
        }
        manifest_path = temp / "manifest.json"
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

        with tarfile.open(temporary, "w:gz", dereference=False) as tar:
            tar.add(manifest_path, arcname="manifest.json", recursive=False)
            data_rel = _data_dir().relative_to("/")
            tar.add(db_snapshot, arcname=f"payload/{data_rel}/sg-gateway.sqlite", recursive=False)
            for source in roots:
                _add_path(tar, source, f"payload/{source.relative_to('/')}")
            for source in data_paths:
                _add_path(tar, source, f"payload/{source.relative_to('/')}")

    os.replace(temporary, destination)
    _set_download_permissions(destination)
    return {
        "name": destination.name,
        "path": str(destination),
        "size_bytes": destination.stat().st_size,
        "sha256": _sha256(destination),
        "source_version": _version(),
        "certificates": bool(_letsencrypt_certificate_domains()),
        "certificate_domains": _letsencrypt_certificate_domains(),
    }


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _validate_members(
    tar: tarfile.TarFile,
    extraction_root: Path,
    members: list[tarfile.TarInfo] | None = None,
) -> None:
    members = tar.getmembers() if members is None else list(members)
    if not members:
        raise RuntimeError("Backup archive is empty")
    for member in members:
        name = member.name
        if name == "manifest.json":
            continue
        if not name.startswith("payload/"):
            raise RuntimeError(f"Unexpected archive member: {name}")
        target = (extraction_root / name).resolve(strict=False)
        if not _is_within(target, extraction_root.resolve(strict=False)):
            raise RuntimeError(f"Unsafe archive path: {name}")
        if member.islnk():
            raise RuntimeError(f"Hard links are not allowed in backup: {name}")
        # FULL_BACKUP_SAFE_NGINX_SYMLINK_FIX1
        if member.issym():
            link = Path(member.linkname)
            if link.is_absolute():
                if (
                    name == "payload/etc/nginx/sites-enabled/sg-gateway"
                    and member.linkname == "/etc/nginx/sites-available/sg-gateway"
                ):
                    # Compatibility with FULL BACKUP V1. Never extract an
                    # absolute link: rewrite it to stay inside payload.
                    member.linkname = "../sites-available/sg-gateway"
                    link = Path(member.linkname)
                else:
                    raise RuntimeError(f"Absolute symlink is not allowed: {name}")
            resolved_link = (target.parent / link).resolve(strict=False)
            payload_root = (extraction_root / "payload").resolve(strict=False)
            if not _is_within(resolved_link, payload_root):
                raise RuntimeError(f"Symlink escapes payload: {name}")


def _read_manifest(path: Path) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("format") != FORMAT or int(payload.get("format_version") or 0) != FORMAT_VERSION:
        raise RuntimeError("Unsupported SG-Gateway full backup format")
    return payload


def _read_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.is_file():
        return values
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        values[key.strip()] = value
    return values


def _write_env_merged(source: Path, destination: Path, preserve: set[str], current: dict[str, str]) -> None:
    source_lines = source.read_text(encoding="utf-8").splitlines()
    seen: set[str] = set()
    output: list[str] = []
    for line in source_lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            key = stripped.split("=", 1)[0].strip()
            seen.add(key)
            if key in preserve and key in current:
                output.append(f"{key}={current[key]}")
                continue
        output.append(line)
    for key in sorted(preserve):
        if key in current and key not in seen:
            output.append(f"{key}={current[key]}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text("\n".join(output) + "\n", encoding="utf-8")
    os.chmod(destination, 0o600)


# FULL_BACKUP_PANEL_DATA_PERMISSIONS_FIX3
def _normalize_panel_data_permissions() -> None:
    uid, gid = _panel_ids()
    data_dir = _data_dir()
    data_dir.mkdir(parents=True, exist_ok=True)
    os.chown(data_dir, uid, gid)
    os.chmod(data_dir, 0o750)

    database = data_dir / "sg-gateway.sqlite"
    if database.is_file():
        os.chown(database, uid, gid)
        os.chmod(database, 0o600)

    backups = data_dir / "backups"
    if backups.exists() and backups.is_dir():
        os.chown(backups, uid, gid)
        os.chmod(backups, 0o750)

    security = data_dir / "security"
    if security.exists() and security.is_dir():
        os.chown(security, uid, gid)
        os.chmod(security, 0o750)


# SG_GATEWAY_02111_XRAY_FULL_ACCESS_RESTORE_FIX
def _normalize_xray_full_access() -> None:
    root = Path("/usr/local/etc/xray")
    if not root.exists():
        return
    result = subprocess.run(
        ["chmod", "-R", "777", str(root)],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(
            "Cannot apply full Xray permissions: "
            + (result.stderr or result.stdout or "chmod failed").strip()[-800:]
        )


def _security_state_dir_from_current_env() -> Path:
    current = _read_env(CONFIG_DIR / "sg-gateway.env")
    configured = str(current.get("SG_GATEWAY_SECURITY_STATE_DIR") or "").strip()
    return Path(configured) if configured else _data_dir() / "security"


def _restored_tls_state() -> dict:
    path = _security_state_dir_from_current_env() / "tls-state.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _restored_certificate_ready() -> tuple[bool, str]:
    state = _restored_tls_state()
    domain = str(state.get("domain") or "").strip()
    if not domain or state.get("https_ready") is False:
        return False, domain
    cert = Path(str(state.get("certificate_path") or f"/etc/letsencrypt/live/{domain}/fullchain.pem"))
    key = Path(str(state.get("key_path") or f"/etc/letsencrypt/live/{domain}/privkey.pem"))
    if not cert.is_file() or not key.is_file():
        return False, domain
    openssl = shutil.which("openssl")
    if not openssl:
        return False, domain
    result = _probe([openssl, "x509", "-in", str(cert), "-noout"], timeout=20)
    return result.returncode == 0, domain


def _restart_xray_required() -> None:
    config = Path("/usr/local/etc/xray/config.json")
    if not config.is_file():
        raise RuntimeError("Restored Xray config.json is missing")
    _normalize_xray_full_access()
    result = _probe(["systemctl", "restart", "xray.service"], timeout=90)
    active = _probe(["systemctl", "is-active", "--quiet", "xray.service"], timeout=20)
    if result.returncode != 0 or active.returncode != 0:
        status = _probe(["systemctl", "status", "xray.service", "--no-pager", "-l"], timeout=20)
        detail = (status.stdout or status.stderr or result.stderr or result.stdout or "").strip()[-1600:]
        raise RuntimeError("Xray did not become active after restore: " + detail)


# SG_GATEWAY_02111_RESTORE_LOCAL_HTTPS_REFRESH_FIX
# SG_GATEWAY_02111_RESTORE_HTTPS_BOOTSTRAP_FIX
def _refresh_restored_https_from_local_files(*, allow_xray_inactive: bool = False) -> bool:
    ready, domain = _restored_certificate_ready()
    if not domain:
        return False
    if not ready:
        raise RuntimeError(
            f"Restored HTTPS state exists for {domain}, but fullchain.pem/privkey.pem are not usable"
        )
    script = Path("/opt/sg-gateway/deploy/configure-panel-access.sh")
    if not script.is_file():
        raise RuntimeError("configure-panel-access.sh is missing after restore")
    env = dict(os.environ)
    if allow_xray_inactive:
        env["SG_GATEWAY_HTTPS_DEFER_XRAY_CHECK"] = "1"
    result = _probe(
        ["/bin/bash", str(script), "--mode", "refresh"],
        timeout=420,
        env=env,
    )
    output = (result.stdout or result.stderr or "").strip()
    if output:
        print(output[-12000:], flush=True)
    if result.returncode != 0:
        detail = output[-2400:]
        raise RuntimeError("Local HTTPS refresh failed after restore: " + detail)
    return True


def _runtime_subprocess_env() -> dict[str, str]:
    env = dict(os.environ)
    for path in (
        CONFIG_DIR / "sg-gateway.env",
        CONFIG_DIR / "runtime.env",
        CONFIG_DIR / "engine-secrets.env",
    ):
        for key, raw in _read_env(path).items():
            value = raw.strip()
            try:
                parsed = shlex.split(value, posix=True)
                if parsed:
                    value = parsed[0]
            except ValueError:
                if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
                    value = value[1:-1]
            env[key] = value
    env["PYTHONPATH"] = "/opt/sg-gateway:/opt/sg-gateway/hostd"
    return env


# SG_GATEWAY_02111_RESTORE_CLIENT_RUNTIME_REQUIRED
def _apply_client_runtime_required() -> None:
    python = Path("/opt/sg-gateway/.venv/bin/python")
    if not python.is_file():
        raise RuntimeError("SG-Gateway venv Python is missing")
    code = (
        "import json,sys; "
        "from sg_hostd.client_runtime import apply_all_clients; "
        "r=apply_all_clients(); "
        "print(json.dumps(r,ensure_ascii=False,indent=2,default=str)); "
        "bad=[e for e in r.get('engines',[]) if not e.get('ok')]; "
        "sys.exit(0 if r.get('ok') and not bad else 1)"
    )
    result = _probe([str(python), "-c", code], timeout=420, env=_runtime_subprocess_env())
    output = (result.stdout or result.stderr or "").strip()
    if output:
        print(output[-16000:], flush=True)
    if result.returncode != 0:
        detail = output[-3200:]
        raise RuntimeError("Client runtime apply failed after restore: " + detail)


def _validate_database_as_panel_user() -> None:
    database = _data_dir() / "sg-gateway.sqlite"
    python = Path("/opt/sg-gateway/.venv/bin/python")
    runuser = shutil.which("runuser")
    if not python.is_file() or not runuser:
        raise RuntimeError("Cannot validate SQLite as sg-gateway: runuser/python missing")
    code = (
        "import sqlite3,sys; "
        "c=sqlite3.connect(sys.argv[1]); "
        "r=c.execute('PRAGMA integrity_check').fetchone(); "
        "c.close(); "
        "assert r and str(r[0]).lower()=='ok'"
    )
    result = _probe(
        [runuser, "-u", PANEL_USER, "--", str(python), "-c", code, str(database)],
        timeout=30,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()[-800:]
        raise RuntimeError("Panel user cannot open restored SQLite: " + detail)


def _remove_destination(path: Path) -> None:
    if path.is_symlink() or path.is_file():
        path.unlink(missing_ok=True)
    elif path.is_dir():
        shutil.rmtree(path)


def _copy_overlay(source: Path, destination: Path) -> None:
    if source.is_symlink():
        destination.parent.mkdir(parents=True, exist_ok=True)
        _remove_destination(destination)
        destination.symlink_to(os.readlink(source))
        return
    if source.is_dir():
        if destination.is_symlink() or (destination.exists() and not destination.is_dir()):
            _remove_destination(destination)
        destination.mkdir(parents=True, exist_ok=True)
        for child in source.iterdir():
            _copy_overlay(child, destination / child.name)
        try:
            shutil.copystat(source, destination, follow_symlinks=False)
        except OSError:
            pass
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    _remove_destination(destination)
    shutil.copy2(source, destination, follow_symlinks=False)


def _destination_public_address() -> str:
    runtime = _read_env(CONFIG_DIR / "runtime.env")
    sg = _read_env(CONFIG_DIR / "sg-gateway.env")
    return str(
        runtime.get("SG_GATEWAY_PUBLIC_ADDRESS")
        or sg.get("SG_GATEWAY_PUBLIC_ADDRESS")
        or sg.get("SG_GATEWAY_HOST")
        or ""
    ).strip()


def _rebind_connection_hosts_to_destination() -> None:
    # SG_GATEWAY_02111_PORTABLE_HOST_REBIND
    host = _destination_public_address()
    if not host:
        raise RuntimeError("Destination public address is missing after restore")
    database = _data_dir() / "sg-gateway.sqlite"
    connection = sqlite3.connect(database)
    try:
        connection.execute(
            "UPDATE connection_settings SET host = ?, updated_at = CURRENT_TIMESTAMP",
            (host,),
        )
        # A transaction captured on the source VPS must never survive a portable
        # restore and override the destination host/runtime on the next apply.
        connection.execute(
            "UPDATE runtime_settings_transactions "
            "SET status = 'rolled_back_portable_restore', finished_at = CURRENT_TIMESTAMP "
            "WHERE status = 'pending'"
        )
        connection.commit()
    finally:
        connection.close()


def _clear_generated_runtime_before_rebuild() -> None:
    # SG_GATEWAY_02111_REGENERATE_RUNTIME_FROM_STATE
    for path in GENERATED_RUNTIME_PATHS:
        _remove_destination(path)
    candidates = _data_dir() / "runtime-candidates"
    if candidates.exists():
        shutil.rmtree(candidates)


def _restore_payload(payload_root: Path, preserve_machine_env: bool = True) -> None:
    current_sg = _read_env(CONFIG_DIR / "sg-gateway.env")
    current_runtime = _read_env(CONFIG_DIR / "runtime.env")

    # Portable restore V2: restore source-of-truth state only.  Never overlay
    # Xray/AWG/Mihomo/sing-box/Nginx runtime generated on the old machine.
    roots = PORTABLE_STATE_ROOTS if preserve_machine_env else ROOT_COMPONENTS
    for root in roots:
        source = payload_root / root.relative_to("/")
        if not source.exists() and not source.is_symlink():
            continue
        if root == CONFIG_DIR:
            for child in source.iterdir():
                if child.name in {"sg-gateway.env", "runtime.env"}:
                    continue
                _copy_overlay(child, root / child.name)
        else:
            _copy_overlay(source, root)

    data_root = payload_root / _data_dir().relative_to("/")
    for name in DATA_COMPONENTS:
        source = data_root / name
        if source.exists() or source.is_symlink():
            _copy_overlay(source, _data_dir() / name)

    db_source = data_root / "sg-gateway.sqlite"
    if not db_source.is_file():
        raise RuntimeError("Backup does not contain sg-gateway.sqlite")
    db_tmp = _data_dir() / ".sg-gateway.sqlite.full-restore"
    shutil.copy2(db_source, db_tmp)
    check = sqlite3.connect(db_tmp)
    try:
        row = check.execute("PRAGMA integrity_check").fetchone()
        if not row or str(row[0]).lower() != "ok":
            raise RuntimeError("Restored SQLite integrity_check failed")
    finally:
        check.close()
    os.replace(db_tmp, _data_dir() / "sg-gateway.sqlite")
    _normalize_panel_data_permissions()

    env_root = payload_root / CONFIG_DIR.relative_to("/")
    sg_source = env_root / "sg-gateway.env"
    runtime_source = env_root / "runtime.env"
    if sg_source.is_file():
        _write_env_merged(
            sg_source,
            CONFIG_DIR / "sg-gateway.env",
            PRESERVE_SG_ENV if preserve_machine_env else set(),
            current_sg,
        )
    if runtime_source.is_file():
        _write_env_merged(
            runtime_source,
            CONFIG_DIR / "runtime.env",
            PRESERVE_RUNTIME_ENV if preserve_machine_env else set(),
            current_runtime,
        )

    if preserve_machine_env:
        _rebind_connection_hosts_to_destination()
        _clear_generated_runtime_before_rebuild()
    _normalize_xray_full_access()


def _ensure_full_restore_upload_nginx() -> None:
    # Full Backup uploads are intentionally unlimited at nginx level.
    # The natural limit is available disk space; the Python stager streams to disk.
    path = Path("/etc/nginx/sites-available/sg-gateway")
    if not path.is_file():
        return
    body = path.read_text(encoding="utf-8")
    endpoint = "/maintenance/full-backups/restore"
    pattern = re.compile(
        rf"(?ms)^    location = {re.escape(endpoint)} \{{\n.*?^    \}}\n"
    )
    matches = list(pattern.finditer(body))
    if len(matches) > 1:
        raise RuntimeError(f"Nginx Full Restore proxy location is ambiguous: {len(matches)}")

    if matches:
        match = matches[0]
        block = match.group(0)
        directive = re.compile(r"(?m)^        client_max_body_size\s+[^;]+;$")
        if directive.search(block):
            normalized = directive.sub("        client_max_body_size 0;", block, count=1)
        else:
            normalized = block.replace(
                f"    location = {endpoint} {{\n",
                f"    location = {endpoint} {{\n        client_max_body_size 0;\n",
                1,
            )
        if normalized != block:
            body = body[:match.start()] + normalized + body[match.end():]
            path.write_text(body, encoding="utf-8", newline="\n")
        return

    matches = list(re.finditer(
        r"(?m)^    location / \{\n        proxy_pass http://127\.0\.0\.1:(\d+);\n",
        body,
    ))
    if len(matches) != 1:
        raise RuntimeError(f"Nginx Full Restore proxy location is ambiguous: {len(matches)}")
    match = matches[0]
    port = match.group(1)
    block = (
        "    location = /maintenance/full-backups/restore {\n"
        "        client_max_body_size 0;\n"
        "        client_body_timeout 300s;\n"
        f"        proxy_pass http://127.0.0.1:{port};\n"
        "        proxy_http_version 1.1;\n"
        "        proxy_set_header Host $host;\n"
        "        proxy_set_header X-Real-IP $remote_addr;\n"
        "        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;\n"
        "        proxy_set_header X-Forwarded-Proto https;\n"
        "        proxy_read_timeout 300s;\n"
        "        proxy_send_timeout 300s;\n"
        "    }\n"
    )
    path.write_text(body[:match.start()] + block + body[match.start():], encoding="utf-8", newline="\n")

def _probe(
    command: list[str],
    timeout: int = 30,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
        env=env,
    )


def _validate_runtime_after_restore() -> None:
    _normalize_panel_data_permissions()
    _normalize_xray_full_access()
    _validate_database_as_panel_user()
    _ensure_full_restore_upload_nginx()
    db = sqlite3.connect(_data_dir() / "sg-gateway.sqlite")
    try:
        row = db.execute("PRAGMA integrity_check").fetchone()
        if not row or str(row[0]).lower() != "ok":
            raise RuntimeError("SQLite integrity_check failed after restore")
    finally:
        db.close()

    xray_config = Path("/usr/local/etc/xray/config.json")
    xray = shutil.which("xray") or "/usr/local/bin/xray"
    if xray_config.is_file() and Path(xray).is_file():
        result = _probe([xray, "run", "-test", "-config", str(xray_config)], timeout=45)
        if result.returncode != 0:
            raise RuntimeError("Xray config check failed: " + (result.stderr or result.stdout).strip()[-800:])

    nginx = shutil.which("nginx")
    if nginx:
        result = _probe([nginx, "-t"], timeout=30)
        if result.returncode != 0:
            raise RuntimeError("Nginx config check failed: " + (result.stderr or result.stdout).strip()[-800:])

    awg_quick = shutil.which("awg-quick")
    awg_config = Path("/etc/amnezia/amneziawg/awg0.conf")
    if awg_quick and awg_config.is_file():
        result = _probe([awg_quick, "strip", str(awg_config)], timeout=20)
        if result.returncode != 0:
            raise RuntimeError("AmneziaWG config check failed: " + (result.stderr or result.stdout).strip()[-800:])


def _schedule_panel_restart() -> None:
    subprocess.run(
        [
            "systemd-run",
            "--unit=sg-gateway-full-restore-restart",
            "--collect",
            "--on-active=3s",
            "/bin/systemctl",
            "restart",
            "sg-hostd.service",
            "sg-gateway.service",
        ],
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def _restart_runtime(*, schedule_panel: bool = True) -> None:
    subprocess.run(
        ["systemctl", "daemon-reload"],
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    _restart_xray_required()
    for service in (
        "sg-gateway-awg.service",
        "mihomo.service",
        "sg-gateway-singbox.service",
        "nginx.service",
    ):
        subprocess.run(
            ["systemctl", "try-restart", service],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    if schedule_panel:
        _schedule_panel_restart()


def _extract_archive(archive: Path, target: Path) -> dict:
    with tarfile.open(archive, "r:gz") as tar:
        # FULL_BACKUP_FILTER_INTERNAL_HISTORY_ON_RESTORE_FIX2
        members = [
            member
            for member in tar.getmembers()
            if not _is_internal_history_member(member.name)
        ]
        _validate_members(tar, target, members)
        tar.extractall(target, members=members)
    manifest = target / "manifest.json"
    if not manifest.is_file():
        raise RuntimeError("manifest.json is missing")
    return _read_manifest(manifest)


def restore_uploaded_full_backup() -> dict:
    _ensure_dirs()
    archive = _backup_dir() / RESTORE_UPLOAD_NAME
    if not archive.is_file():
        raise RuntimeError("Uploaded .sgbackup file not found")

    # Validate the upload completely before touching the live server.
    _restore_progress("[Restore 1/7] Проверяю структуру и безопасность .sgbackup")
    with tempfile.TemporaryDirectory(prefix="restore-", dir=_work_dir()) as temp_name:
        temp = Path(temp_name)
        manifest = _extract_archive(archive, temp)
        payload = temp / "payload"
        db_path = payload / _data_dir().relative_to("/") / "sg-gateway.sqlite"
        if not db_path.is_file():
            raise RuntimeError("Backup does not contain the SG-Gateway database")
        db = sqlite3.connect(db_path)
        try:
            row = db.execute("PRAGMA integrity_check").fetchone()
            if not row or str(row[0]).lower() != "ok":
                raise RuntimeError("Uploaded SQLite database is damaged")
        finally:
            db.close()

        # SG_GATEWAY_02206_RESTORE_RUNTIME_CONTRACT_V1
        # A portable restore must never touch the live server when the clean
        # destination installation is already missing a required runtime.
        from sg_hostd.runtime_contracts import assert_runtime_contract

        assert_runtime_contract(
            database_path=db_path,
            strict_optional=True,
            include_all_critical=True,
        )
        _restore_progress("[Restore 2/7] Backup, SQLite и Runtime Contract проверены")
        _restore_progress("[Restore 3/7] Создаю страховочный полный backup текущего сервера")
        safety = create_full_backup_archive(prefix="SG-Gateway-SAFETY")
        try:
            _restore_progress("[Restore 4/7] Восстанавливаю клиентов, ключи, runtime, HTTPS и сертификаты")
            _restore_payload(payload, preserve_machine_env=True)
            _restore_progress("[Restore 5/7] Проверяю SQLite и исходные данные; runtime будет создан заново")
            _normalize_panel_data_permissions()
            _validate_database_as_panel_user()
            _restore_progress("[Restore 6/7] Возвращаю локальный HTTPS и пересобираю все протоколы на новом сервере")
            cert_ready, cert_domain = _restored_certificate_ready()
            if cert_domain:
                state = _restored_tls_state()
                panel_port = int(state.get("public_port") or state.get("panel_port") or 443)
                suffix = "" if panel_port == 443 else f":{panel_port}"
                _restore_progress(f"[Restore 6/7] Адрес панели после переключения: https://{cert_domain}{suffix}")
                # Break the HTTPS/Xray circular dependency: first restore Nginx/TLS
                # from the already-restored local certificate without requiring
                # Xray to be active. Runtime rebuild below starts Xray, then a
                # second strict refresh verifies the complete 443 contract.
                _refresh_restored_https_from_local_files(allow_xray_inactive=True)
            _apply_client_runtime_required()
            _normalize_xray_full_access()
            _restart_xray_required()
            if cert_domain:
                _refresh_restored_https_from_local_files(allow_xray_inactive=False)
                _apply_client_runtime_required()
                _normalize_xray_full_access()
                _restart_xray_required()
            _validate_runtime_after_restore()
            cert_ready, cert_domain = _restored_certificate_ready()
            if cert_domain and not cert_ready:
                raise RuntimeError(f"Restored certificate validation failed for {cert_domain}")
            _schedule_panel_restart()
            _restore_progress("[Restore 7/7] Full Restore завершён: runtime пересобран на новом сервере")
        except Exception:
            _restore_progress("[Restore] ОШИБКА. Автоматически возвращаю страховочный backup")
            # Safety restore is best-effort but automatic. It uses the same
            # validated format and keeps this machine's public address.
            safety_path = Path(str(safety["path"]))
            with tempfile.TemporaryDirectory(prefix="rollback-", dir=_work_dir()) as rollback_name:
                rollback = Path(rollback_name)
                _extract_archive(safety_path, rollback)
                _restore_payload(rollback / "payload", preserve_machine_env=False)
                _normalize_panel_data_permissions()
                _restart_runtime()
            _restore_progress("[Restore] Rollback страховочного backup выполнен")
            raise

    archive.unlink(missing_ok=True)
    cert_ready, cert_domain = _restored_certificate_ready()
    return {
        "source_version": str(manifest.get("source_version") or "unknown"),
        "safety_backup": str(safety.get("name") or ""),
        "certificates": cert_ready,
        "certificate_domain": cert_domain,
        "xray_active": _probe(["systemctl", "is-active", "--quiet", "xray.service"], timeout=20).returncode == 0,
        "client_runtime_applied": True,
        "portable_runtime_regenerated": True,
        "message": "Full backup restored; destination public IP preserved; all runtime regenerated from restored state",
    }
