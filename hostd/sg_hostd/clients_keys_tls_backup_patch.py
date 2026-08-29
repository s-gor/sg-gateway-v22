from __future__ import annotations

import configparser
import json
import os
import re
import shutil
import sqlite3
import tarfile
import tempfile
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from types import ModuleType


DOMAIN_RE = re.compile(
    r"^(?=.{4,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$"
)
CANONICAL_LETSENCRYPT = Path("/etc/letsencrypt")
TLS_STATE_NAME = "tls-state.json"
XRAY_PROFILE_FLAGS = {
    "reality_tcp": "reality_tcp_enabled",
    "xhttp_reality": "xhttp_reality_enabled",
    "xhttp_tls": "xhttp_tls_enabled",
    "hysteria2": "hysteria2_enabled",
}
CRITICAL_ENGINES = ("amneziawg", "amneziawg3", "xray")


def _bool(value: object, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on", "enabled"}


def _domain(value: object) -> str:
    normalized = str(value or "").strip().lower().rstrip(".")
    return normalized if DOMAIN_RE.fullmatch(normalized) else ""


def _read_json(path: Path) -> dict:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _portable_tls_state(source: dict, domain: str) -> dict:
    certificate = source.get("certificate")
    return {
        "domain": domain,
        "https_ready": True,
        "certificate": dict(certificate) if isinstance(certificate, dict) else {},
        "certificate_path": f"/etc/letsencrypt/live/{domain}/fullchain.pem",
        "key_path": f"/etc/letsencrypt/live/{domain}/privkey.pem",
        "updated_at": str(source.get("updated_at") or datetime.now(timezone.utc).isoformat()),
        "portable_clients_keys": True,
    }


def _tls_source(
    data: ModuleType,
    *,
    source_data_dir: Path | None,
    source_letsencrypt_dir: Path | None,
) -> tuple[dict, str, Path]:
    data_dir = Path(source_data_dir or data.full._data_dir())
    state_path = data_dir / "security" / TLS_STATE_NAME
    if source_data_dir is None and not state_path.is_file():
        try:
            candidate = data.full._security_state_dir_from_current_env() / TLS_STATE_NAME
        except Exception:
            candidate = state_path
        if candidate.is_file():
            state_path = candidate
    state = _read_json(state_path)
    domain = _domain(state.get("domain"))
    letsencrypt = Path(source_letsencrypt_dir or CANONICAL_LETSENCRYPT)
    if not domain:
        return {}, "", letsencrypt
    live = letsencrypt / "live" / domain
    if not (live / "fullchain.pem").is_file() or not (live / "privkey.pem").is_file():
        return {}, "", letsencrypt
    return _portable_tls_state(state, domain), domain, letsencrypt


def _renewal_account_paths(letsencrypt: Path, domain: str) -> list[Path]:
    renewal = letsencrypt / "renewal" / f"{domain}.conf"
    if not renewal.is_file():
        return []
    parser = configparser.RawConfigParser()
    try:
        parser.read(renewal, encoding="utf-8")
    except (OSError, configparser.Error):
        return []
    account = ""
    try:
        account = str(parser.get("renewalparams", "account", fallback="") or "").strip()
    except configparser.Error:
        account = ""
    if not account or "/" in account or "\\" in account or account in {".", ".."}:
        return []
    root = letsencrypt / "accounts"
    if not root.is_dir():
        return []
    matches: list[Path] = []
    try:
        for candidate in root.glob(f"*/*/{account}"):
            if candidate.is_dir():
                matches.append(candidate)
    except OSError:
        return []
    return sorted(matches)


def _certificate_sources(letsencrypt: Path, domain: str) -> list[tuple[Path, str]]:
    sources: list[tuple[Path, str]] = []
    for relative in (
        Path("live") / domain,
        Path("archive") / domain,
        Path("renewal") / f"{domain}.conf",
    ):
        source = letsencrypt / relative
        if source.exists() or source.is_symlink():
            sources.append((source, f"payload/etc/letsencrypt/{relative.as_posix()}"))
    for account in _renewal_account_paths(letsencrypt, domain):
        relative = account.relative_to(letsencrypt)
        sources.append((account, f"payload/etc/letsencrypt/{relative.as_posix()}"))
    return sources


def _rewrite_created_archive(
    data: ModuleType,
    archive: Path,
    *,
    tls_state: dict,
    domain: str,
    letsencrypt: Path,
) -> None:
    with tempfile.TemporaryDirectory(prefix="clients-keys-tls-") as temp_name:
        temp = Path(temp_name)
        extracted = temp / "original"
        extracted.mkdir()
        manifest = data._extract_archive(archive, extracted)
        db = (
            extracted
            / "payload"
            / data.CANONICAL_DATA_DIR.relative_to("/")
            / "sg-gateway.sqlite"
        )
        if not db.is_file():
            raise RuntimeError("Clients & Keys backup database disappeared during TLS packaging")

        state = temp / TLS_STATE_NAME
        state.write_text(
            json.dumps(tls_state, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        os.chmod(state, 0o600)

        sources = _certificate_sources(letsencrypt, domain)
        if not sources:
            raise RuntimeError(f"TLS certificate material for {domain} is incomplete")
        manifest.update(
            {
                "contains_letsencrypt": True,
                "contains_letsencrypt_certificates": True,
                "certificate_domains": [domain],
                "certificate_policy": "active SG-Gateway HTTPS identity only",
                "portable_restore": (
                    "client identities and active HTTPS certificate are rebound to destination server settings"
                ),
                "components": [
                    str(data.CANONICAL_DATA_DIR / "sg-gateway.sqlite"),
                    str(data.CANONICAL_DATA_DIR / "security" / TLS_STATE_NAME),
                    *[
                        "/" + arc.removeprefix("payload/")
                        for _, arc in sources
                    ],
                ],
            }
        )
        excluded = [str(item) for item in manifest.get("excluded", [])]
        manifest["excluded"] = [
            item for item in excluded if item != "HTTPS and certificates"
        ]
        manifest_path = temp / "manifest.json"
        manifest_path.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

        temporary = archive.with_name(f".{archive.name}.tls.tmp")
        temporary.unlink(missing_ok=True)
        with tarfile.open(temporary, "w:gz", dereference=False) as tar:
            tar.add(manifest_path, arcname="manifest.json", recursive=False)
            tar.add(
                db,
                arcname=(
                    f"payload/{data.CANONICAL_DATA_DIR.relative_to('/')}/sg-gateway.sqlite"
                ),
                recursive=False,
            )
            tar.add(
                state,
                arcname=(
                    f"payload/{data.CANONICAL_DATA_DIR.relative_to('/')}/security/{TLS_STATE_NAME}"
                ),
                recursive=False,
            )
            for source, arcname in sources:
                tar.add(source, arcname=arcname, recursive=True)
        os.replace(temporary, archive)
        os.chmod(archive, 0o600)
        if os.geteuid() == 0:
            uid, gid = data.full._panel_ids()
            os.chown(archive, uid, gid)


def _validate_tls_payload(data: ModuleType, archive: Path, manifest: dict) -> tuple[bool, list[str]]:
    domains = [_domain(item) for item in manifest.get("certificate_domains", [])]
    domains = [item for item in domains if item]
    claimed = bool(manifest.get("contains_letsencrypt_certificates"))
    if not claimed:
        return False, []
    if len(domains) != 1:
        raise RuntimeError("Clients & Keys TLS backup must contain exactly one active certificate domain")
    domain = domains[0]
    with tempfile.TemporaryDirectory(prefix="verify-clients-tls-") as temp_name:
        root = Path(temp_name)
        data._extract_archive(archive, root)
        state = _read_json(
            root
            / "payload"
            / data.CANONICAL_DATA_DIR.relative_to("/")
            / "security"
            / TLS_STATE_NAME
        )
        if _domain(state.get("domain")) != domain:
            raise RuntimeError("Clients & Keys TLS state domain does not match manifest")
        live = root / "payload/etc/letsencrypt/live" / domain
        cert = live / "fullchain.pem"
        key = live / "privkey.pem"
        try:
            valid = cert.is_file() and cert.stat().st_size > 0 and key.is_file() and key.stat().st_size > 0
        except OSError:
            valid = False
        if not valid:
            raise RuntimeError(f"Clients & Keys TLS certificate files are incomplete for {domain}")
    return True, [domain]


def _destination_tls_state(full: ModuleType, portable: dict, domain: str) -> dict:
    sg_env = full._read_env(full.CONFIG_DIR / "sg-gateway.env")
    runtime_env = full._read_env(full.CONFIG_DIR / "runtime.env")

    def integer(value: object, fallback: int) -> int:
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            return fallback
        return parsed if 1 <= parsed <= 65535 else fallback

    public_port = integer(
        sg_env.get("SG_GATEWAY_PUBLIC_PORT")
        or runtime_env.get("SG_GATEWAY_PANEL_PORT"),
        443,
    )
    backend_port = integer(sg_env.get("SG_GATEWAY_PORT"), 18080)
    state = _portable_tls_state(portable, domain)
    state.update(
        {
            "public_port": public_port,
            "panel_port": public_port,
            "backend_port": backend_port,
            "last_action": "portable-restore",
            "last_message": "HTTPS identity imported by Clients & Keys restore",
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
    )
    return state


def _active_destination_tls_domain(full: ModuleType) -> str:
    try:
        state = full._restored_tls_state()
    except Exception:
        return ""
    return _domain(state.get("domain"))


def _rebind_tls_client_hosts(database: Path, domain: str) -> None:
    if not domain:
        return
    con = sqlite3.connect(database, timeout=15)
    try:
        rows = con.execute(
            "SELECT id, engine, config_json FROM device_credentials WHERE engine IN ('anytls', 'tuic')"
        ).fetchall()
        for row_id, engine, raw in rows:
            try:
                payload = json.loads(raw or "{}")
            except (TypeError, ValueError, json.JSONDecodeError):
                continue
            if not isinstance(payload, dict):
                continue
            payload["host"] = domain
            payload["server_name"] = domain
            con.execute(
                "UPDATE device_credentials SET config_json = ? WHERE id = ?",
                (json.dumps(payload, ensure_ascii=False, sort_keys=True), int(row_id)),
            )
        con.commit()
    finally:
        con.close()


def _runtime_contract_for_destination(data: ModuleType, database_path: Path) -> dict:
    from sg_hostd import runtime_contracts

    db = sqlite3.connect(database_path, timeout=15)
    try:
        tables = data._table_names(db)
        settings: dict[str, bool] = {}
        if "connection_settings" in tables:
            for engine, enabled in db.execute(
                "SELECT engine, enabled FROM connection_settings"
            ).fetchall():
                settings[str(engine)] = bool(enabled)
        active_credentials = {
            str(row[0] or "").strip().lower()
            for row in db.execute(
                "SELECT DISTINCT engine FROM device_credentials WHERE status != 'disabled'"
            ).fetchall()
            if str(row[0] or "").strip()
        }
    finally:
        db.close()

    checks: list[dict] = []
    failures: list[dict] = []
    for engine in CRITICAL_ENGINES:
        if engine not in active_credentials or not settings.get(engine, True):
            continue
        spec = runtime_contracts.DEFAULT_SPECS[engine]
        missing: list[str] = []
        for requirement in spec.requirements:
            ready, detail = runtime_contracts._requirement_ready(requirement)
            if not ready:
                missing.append(f"{requirement.label}: {detail}")
        item = {"engine": engine, "ready": not missing, "missing": missing}
        checks.append(item)
        if missing:
            failures.append(item)
    if failures:
        detail = "; ".join(
            f"{item['engine']}: {', '.join(item['missing'])}" for item in failures
        )
        raise runtime_contracts.RuntimeContractError(
            "Runtime Contract для переносимого restore не пройден. "
            "Выключенные на новом сервере протоколы пропущены. " + detail
        )
    return {
        "ok": True,
        "checks": checks,
        "profile": "clients-and-keys",
        "disabled_destination_protocols_skipped": True,
    }


def _promote_uploaded_data_backup(data: ModuleType) -> dict:
    directory = data._data_backup_dir()
    archive = directory / data.RESTORE_UPLOAD_NAME
    if not archive.is_file():
        raise RuntimeError("Uploaded Clients & Keys .sgbackup file for restore not found")

    with tempfile.TemporaryDirectory(prefix="promote-clients-tls-", dir=data._work_dir()) as temp_name:
        temp = Path(temp_name)
        manifest = data._extract_archive(archive, temp)
        source_db = (
            temp
            / "payload"
            / data.CANONICAL_DATA_DIR.relative_to("/")
            / "sg-gateway.sqlite"
        )
        data._verify_database(source_db)

        source_tls_domain = ""
        source_tls_state: dict = {}
        if manifest.get("contains_letsencrypt_certificates"):
            _valid, domains = _validate_tls_payload(data, archive, manifest)
            source_tls_domain = domains[0] if domains else ""
            source_tls_state = _read_json(
                temp
                / "payload"
                / data.CANONICAL_DATA_DIR.relative_to("/")
                / "security"
                / TLS_STATE_NAME
            )

        destination_domain = _active_destination_tls_domain(data.full)
        import_tls = bool(
            source_tls_domain
            and (not destination_domain or destination_domain == source_tls_domain)
        )
        selected_tls_domain = source_tls_domain if import_tls else destination_domain
        certificate_policy = (
            "imported"
            if import_tls
            else (
                "destination-preserved-domain-mismatch"
                if source_tls_domain and destination_domain and source_tls_domain != destination_domain
                else "none"
            )
        )

        merged_db = temp / "merged-sg-gateway.sqlite"
        data._build_merged_destination_database(source_db, merged_db)
        if import_tls and selected_tls_domain:
            _rebind_tls_client_hosts(merged_db, selected_tls_domain)
        contract = _runtime_contract_for_destination(data, merged_db)

        data.full._ensure_dirs()
        destination = data.full._backup_dir() / data.full.RESTORE_UPLOAD_NAME
        temporary = destination.with_name(f".{destination.name}.clients-tls-promote.tmp")
        destination.unlink(missing_ok=True)
        temporary.unlink(missing_ok=True)

        full_components = [str(data.CANONICAL_DATA_DIR / "sg-gateway.sqlite")]
        promoted_tls_state: Path | None = None
        if import_tls:
            promoted_tls_state = temp / "promoted-tls-state.json"
            promoted_tls_state.write_text(
                json.dumps(
                    _destination_tls_state(data.full, source_tls_state, source_tls_domain),
                    ensure_ascii=False,
                    indent=2,
                    sort_keys=True,
                )
                + "\n",
                encoding="utf-8",
            )
            os.chmod(promoted_tls_state, 0o600)
            full_components.extend(
                [
                    str(data.CANONICAL_DATA_DIR / "security" / TLS_STATE_NAME),
                    "/etc/letsencrypt",
                ]
            )

        full_manifest = {
            "format": data.full.FORMAT,
            "format_version": data.full.FORMAT_VERSION,
            "created_at": str(
                manifest.get("created_at") or datetime.now(timezone.utc).isoformat()
            ),
            "source_version": str(manifest.get("source_version") or "unknown"),
            "contains_private_keys": True,
            "contains_letsencrypt": import_tls,
            "contains_letsencrypt_certificates": import_tls,
            "certificate_domains": [source_tls_domain] if import_tls else [],
            "certificate_policy": certificate_policy,
            "portable_restore": "destination server settings and protocol enablement are preserved",
            "excluded_history": ["security/backups", "security/jobs"],
            "components": full_components,
            "data_profile": True,
            "clients_keys_profile": True,
            "clients_keys_tls_profile": bool(import_tls),
            "promoted_from": data.FORMAT,
        }
        manifest_path = temp / "promoted-full-manifest.json"
        manifest_path.write_text(
            json.dumps(full_manifest, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

        with tarfile.open(temporary, "w:gz", dereference=False) as tar:
            tar.add(manifest_path, arcname="manifest.json", recursive=False)
            tar.add(
                merged_db,
                arcname=f"payload/{data.CANONICAL_DATA_DIR.relative_to('/')}/sg-gateway.sqlite",
                recursive=False,
            )
            if import_tls and promoted_tls_state is not None:
                tar.add(
                    promoted_tls_state,
                    arcname=(
                        f"payload/{data.CANONICAL_DATA_DIR.relative_to('/')}/security/{TLS_STATE_NAME}"
                    ),
                    recursive=False,
                )
                extracted_le = temp / "payload/etc/letsencrypt"
                if extracted_le.is_dir():
                    tar.add(
                        extracted_le,
                        arcname="payload/etc/letsencrypt",
                        recursive=True,
                    )

        os.replace(temporary, destination)
        os.chmod(destination, 0o600)
        archive.unlink(missing_ok=True)
        return {
            "promoted": True,
            "source_version": str(manifest.get("source_version") or "unknown"),
            "runtime_contract": contract,
            "full_restore_upload": str(destination),
            "profile": "clients-and-keys",
            "certificates": import_tls,
            "certificate_domain": source_tls_domain if import_tls else destination_domain,
            "certificate_policy": certificate_policy,
        }


def _connection_policy(database: sqlite3.Connection) -> tuple[dict[str, bool], set[str]]:
    settings: dict[str, bool] = {}
    xray_profiles = {"reality_tcp", "xhttp_reality"}
    try:
        rows = database.execute(
            "SELECT engine, enabled, config_json FROM connection_settings"
        ).fetchall()
    except sqlite3.Error:
        return settings, xray_profiles
    for engine_raw, enabled_raw, config_raw in rows:
        engine = str(engine_raw or "").strip().lower()
        settings[engine] = bool(enabled_raw)
        if engine != "xray":
            continue
        try:
            config = json.loads(config_raw or "{}")
        except (TypeError, ValueError, json.JSONDecodeError):
            config = {}
        if not isinstance(config, dict):
            config = {}
        selected: set[str] = set()
        for profile, flag in XRAY_PROFILE_FLAGS.items():
            default = profile in {"reality_tcp", "xhttp_reality"}
            if _bool(config.get(flag), default):
                selected.add(profile)
        if selected:
            xray_profiles = selected
    return settings, xray_profiles


@contextmanager
def destination_protocol_policy(database_path: Path):
    """Temporarily hide imported protocols/profiles disabled on destination.

    The original portable client credentials are restored after runtime generation,
    so enabling a protocol later can reuse the migrated client identity.
    """

    db = sqlite3.connect(database_path, timeout=15)
    snapshots: list[tuple[int, str, str | None]] = []
    try:
        settings, enabled_xray_profiles = _connection_policy(db)
        rows = db.execute(
            "SELECT id, engine, status, config_json FROM device_credentials ORDER BY id"
        ).fetchall()
        for row_id, engine_raw, status, raw in rows:
            engine = str(engine_raw or "").strip().lower()
            if engine not in CRITICAL_ENGINES:
                continue
            snapshots.append((int(row_id), str(status), raw))
            if not settings.get(engine, True):
                db.execute(
                    "UPDATE device_credentials SET status = 'disabled' WHERE id = ?",
                    (int(row_id),),
                )
                continue
            if engine != "xray":
                continue
            try:
                payload = json.loads(raw or "{}")
            except (TypeError, ValueError, json.JSONDecodeError):
                payload = {}
            if not isinstance(payload, dict):
                payload = {}
            selected = payload.get("profiles")
            if not isinstance(selected, list) or not selected:
                selected = ["reality_tcp", "xhttp_reality"]
            active = [
                str(item)
                for item in selected
                if str(item) in enabled_xray_profiles
            ]
            if not active:
                db.execute(
                    "UPDATE device_credentials SET status = 'disabled' WHERE id = ?",
                    (int(row_id),),
                )
                continue
            if active != [str(item) for item in selected]:
                payload["profiles"] = active
                db.execute(
                    "UPDATE device_credentials SET config_json = ? WHERE id = ?",
                    (json.dumps(payload, ensure_ascii=False, sort_keys=True), int(row_id)),
                )
        db.commit()
        yield {
            "settings": settings,
            "xray_profiles": sorted(enabled_xray_profiles),
        }
    finally:
        try:
            for row_id, status, raw in snapshots:
                db.execute(
                    "UPDATE device_credentials SET status = ?, config_json = ? WHERE id = ?",
                    (status, raw, int(row_id)),
                )
            db.commit()
        finally:
            db.close()


def install(data: ModuleType) -> None:
    original_create = data.create_data_backup_archive
    original_verify = data._verify_archive

    def create_data_backup_archive(
        prefix: str = data.PREFIX,
        *,
        source_data_dir: Path | None = None,
        source_config_dir: Path | None = None,
        source_letsencrypt_dir: Path | None = None,
        destination_dir: Path | None = None,
    ) -> dict:
        result = original_create(
            prefix,
            source_data_dir=source_data_dir,
            source_config_dir=source_config_dir,
            source_letsencrypt_dir=source_letsencrypt_dir,
            destination_dir=destination_dir,
        )
        tls_state, domain, letsencrypt = _tls_source(
            data,
            source_data_dir=source_data_dir,
            source_letsencrypt_dir=source_letsencrypt_dir,
        )
        if not domain:
            return result
        archive = Path(str(result["path"]))
        _rewrite_created_archive(
            data,
            archive,
            tls_state=tls_state,
            domain=domain,
            letsencrypt=letsencrypt,
        )
        result.update(
            {
                "size_bytes": archive.stat().st_size,
                "sha256": data.full._sha256(archive),
                "certificates": True,
                "certificate_domains": [domain],
            }
        )
        return result

    def verify_archive(archive: Path) -> dict:
        result = original_verify(archive)
        with tarfile.open(archive, "r:gz") as tar:
            try:
                member = tar.getmember("manifest.json")
            except KeyError as exc:
                raise RuntimeError("manifest.json is missing") from exc
            stream = tar.extractfile(member)
            if stream is None:
                raise RuntimeError("manifest.json is unreadable")
            manifest = json.loads(stream.read().decode("utf-8"))
        certificates, domains = _validate_tls_payload(data, archive, manifest)
        result.update(
            {
                "contains_letsencrypt": certificates,
                "contains_letsencrypt_certificates": certificates,
                "certificate_domains": domains,
                "components": int(result.get("components") or 1) + (2 if certificates else 0),
            }
        )
        if certificates:
            result.setdefault("checks", {})["tls_identity"] = "ok"
        return result

    data.create_data_backup_archive = create_data_backup_archive
    data._verify_archive = verify_archive
    data.promote_uploaded_data_backup = lambda: _promote_uploaded_data_backup(data)
