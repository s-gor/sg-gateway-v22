from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from types import ModuleType


FILTERED_ENGINES = {
    "amneziawg",
    "amneziawg3",
    "xray",
    "mihomo",
    "anytls",
    "tuic",
}


def _bool(value: object, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on", "enabled"}


def _destination_policy(
    tls: ModuleType,
    database: sqlite3.Connection,
) -> tuple[dict[str, bool], set[str]]:
    enabled: dict[str, bool] = {}
    xray_profiles = {"reality_tcp", "xhttp_reality"}
    try:
        rows = database.execute(
            "SELECT engine, enabled, config_json FROM connection_settings"
        ).fetchall()
    except sqlite3.Error:
        return enabled, xray_profiles

    for engine_raw, enabled_raw, config_raw in rows:
        engine = str(engine_raw or "").strip().lower()
        row_enabled = bool(enabled_raw)
        try:
            config = json.loads(config_raw or "{}")
        except (TypeError, ValueError, json.JSONDecodeError):
            config = {}
        if not isinstance(config, dict):
            config = {}

        if engine == "xray":
            flags_present = any(
                flag in config for flag in tls.XRAY_PROFILE_FLAGS.values()
            )
            if flags_present:
                xray_profiles = {
                    profile
                    for profile, flag in tls.XRAY_PROFILE_FLAGS.items()
                    if _bool(config.get(flag), False)
                }
            else:
                xray_profiles = {"reality_tcp", "xhttp_reality"}
            enabled["xray"] = row_enabled and bool(xray_profiles)
            continue

        if engine == "mihomo":
            enabled["mihomo"] = row_enabled and _bool(
                config.get("mieru_enabled"), True
            )
            enabled["anytls"] = row_enabled and _bool(
                config.get("anytls_enabled"), False
            )
            enabled["tuic"] = row_enabled and _bool(
                config.get("tuic_enabled"), False
            )
            continue

        enabled[engine] = row_enabled

    return enabled, xray_profiles


@contextmanager
def _destination_protocol_policy(tls: ModuleType, database_path: Path):
    """Expose only protocols enabled by the destination during check/apply.

    Imported credential status and Xray profile selections are restored exactly
    after the temporary runtime view. A later manual protocol enable therefore
    reuses the migrated client identity instead of generating new credentials.
    """

    db = sqlite3.connect(database_path, timeout=15)
    snapshots: list[tuple[int, object, object]] = []
    try:
        enabled, enabled_xray_profiles = _destination_policy(tls, db)
        rows = db.execute(
            "SELECT id, engine, status, config_json "
            "FROM device_credentials ORDER BY id"
        ).fetchall()
        for row_id, engine_raw, status, raw in rows:
            engine = str(engine_raw or "").strip().lower()
            if engine not in FILTERED_ENGINES:
                continue
            snapshots.append((int(row_id), status, raw))

            # Missing destination settings are treated as disabled. Portable
            # restore must never invent server protocol enablement.
            if not enabled.get(engine, False):
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
            elif active != [str(item) for item in selected]:
                payload["profiles"] = active
                db.execute(
                    "UPDATE device_credentials SET config_json = ? WHERE id = ?",
                    (
                        json.dumps(payload, ensure_ascii=False, sort_keys=True),
                        int(row_id),
                    ),
                )

        db.commit()
        yield {
            "enabled_engines": dict(enabled),
            "xray_profiles": sorted(enabled_xray_profiles),
        }
    finally:
        try:
            for row_id, status, raw in snapshots:
                db.execute(
                    "UPDATE device_credentials "
                    "SET status = ?, config_json = ? WHERE id = ?",
                    (status, raw, int(row_id)),
                )
            db.commit()
        finally:
            db.close()


def _runtime_contract_for_destination(
    data: ModuleType,
    tls: ModuleType,
    database_path: Path,
) -> dict:
    from sg_hostd import runtime_contracts

    with _destination_protocol_policy(tls, database_path) as policy:
        enabled = policy["enabled_engines"]
        specs = dict(runtime_contracts.DEFAULT_SPECS)
        for engine, spec in list(specs.items()):
            # include_all_critical is still requested from the established
            # contract, but only for critical engines explicitly enabled on
            # the destination. Missing/off protocols are intentionally skipped.
            if spec.critical and not enabled.get(engine, False):
                specs.pop(engine, None)

        result = data.assert_runtime_contract(
            database_path=database_path,
            strict_optional=True,
            include_all_critical=True,
            specs=specs,
        )

    payload = dict(result)
    payload["profile"] = "clients-and-keys"
    payload["disabled_destination_protocols_skipped"] = True
    payload["destination_protocol_enablement_preserved"] = True
    return payload


def _raw_tls_state(
    data: ModuleType,
    tls: ModuleType,
    *,
    source_data_dir: Path | None,
) -> dict:
    data_dir = Path(source_data_dir or data.full._data_dir())
    state_path = data_dir / "security" / tls.TLS_STATE_NAME
    if source_data_dir is None and not state_path.is_file():
        try:
            candidate = (
                data.full._security_state_dir_from_current_env()
                / tls.TLS_STATE_NAME
            )
        except Exception:
            candidate = state_path
        if candidate.is_file():
            state_path = candidate
    return tls._read_json(state_path)


def install(data: ModuleType, tls: ModuleType) -> None:
    if getattr(tls, "_portable_contract_fix_v3_installed", False):
        return

    original_tls_source = tls._tls_source

    def tls_source(
        data_module: ModuleType,
        *,
        source_data_dir: Path | None,
        source_letsencrypt_dir: Path | None,
    ):
        raw_state = _raw_tls_state(
            data_module,
            tls,
            source_data_dir=source_data_dir,
        )
        letsencrypt = Path(
            source_letsencrypt_dir or tls.CANONICAL_LETSENCRYPT
        )
        # The legacy helper normalizes a discovered certificate to
        # https_ready=True. Check the source state before that normalization so
        # stale certificate files can never become a portable HTTPS identity.
        if raw_state and raw_state.get("https_ready") is False:
            return {}, "", letsencrypt

        return original_tls_source(
            data_module,
            source_data_dir=source_data_dir,
            source_letsencrypt_dir=source_letsencrypt_dir,
        )

    def runtime_contract(data_module: ModuleType, database_path: Path) -> dict:
        return _runtime_contract_for_destination(
            data_module,
            tls,
            database_path,
        )

    def destination_policy(database_path: Path):
        return _destination_protocol_policy(tls, database_path)

    tls._tls_source = tls_source
    tls._runtime_contract_for_destination = runtime_contract
    tls.destination_protocol_policy = destination_policy
    tls._portable_contract_fix_v2_installed = True
    tls._portable_contract_fix_v3_installed = True
