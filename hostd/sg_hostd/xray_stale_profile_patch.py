"""Keep stale disabled Xray selections from blocking unrelated client changes."""

from __future__ import annotations

import json
from contextvars import ContextVar
from typing import Any


_XRAY_PROFILE_IDS = frozenset(
    {"reality_tcp", "xhttp_reality", "xhttp_tls", "hysteria2"}
)
_CAPTURE_WARNINGS: ContextVar[bool] = ContextVar(
    "sg_gateway_xray_capture_stale_warnings", default=False
)
_WARNINGS: ContextVar[tuple[str, ...]] = ContextVar(
    "sg_gateway_xray_stale_warnings", default=()
)


def _copy_row(row: Any) -> dict[str, Any]:
    if isinstance(row, dict):
        return dict(row)
    keys = getattr(row, "keys", None)
    if callable(keys):
        return {key: row[key] for key in keys()}
    return dict(row)


def install(client_runtime) -> None:
    """Install the stale-profile filter once on ``sg_hostd.client_runtime``."""
    if getattr(client_runtime, "_sg_xray_stale_profile_patch_installed", False):
        return

    original_deployment_rows = client_runtime._deployment_rows
    original_apply_xray = client_runtime._apply_xray

    def deployment_rows(engine: str, active_only: bool = True):
        rows = original_deployment_rows(engine, active_only=active_only)
        if engine != "xray":
            return rows

        overview = client_runtime.xray_profiles_overview()
        enabled_profiles = {
            str(profile.id)
            for profile in overview["profiles"]
            if profile.enabled
        }
        filtered_rows: list[dict[str, Any]] = []
        warnings = list(_WARNINGS.get())

        for row in rows:
            copied = _copy_row(row)
            config = client_runtime._json(copied.get("config_json"))
            selected = config.get("profiles")
            if not isinstance(selected, list) or not selected:
                selected = ["reality_tcp", "xhttp_reality"]
            selected_ids = [str(profile_id) for profile_id in selected]

            disabled_ids = [
                profile_id
                for profile_id in selected_ids
                if profile_id in _XRAY_PROFILE_IDS
                and profile_id not in enabled_profiles
            ]
            active_ids = [
                profile_id
                for profile_id in selected_ids
                if profile_id in enabled_profiles
            ]

            if disabled_ids and _CAPTURE_WARNINGS.get():
                client_name = str(
                    copied.get("client_name")
                    or copied.get("client_id")
                    or "<неизвестно>"
                )
                for profile_id in disabled_ids:
                    warnings.append(
                        f"Xray-профиль {profile_id} выбран у клиента {client_name}, "
                        "но выключен на сервере; credential пропущен"
                    )

            if not active_ids:
                continue

            config["profiles"] = active_ids
            copied["config_json"] = json.dumps(
                config, ensure_ascii=False, separators=(",", ":")
            )
            filtered_rows.append(copied)

        if _CAPTURE_WARNINGS.get():
            _WARNINGS.set(tuple(dict.fromkeys(warnings)))
        return filtered_rows

    def apply_xray(*, force_profiles: bool = False):
        capture_token = _CAPTURE_WARNINGS.set(True)
        warnings_token = _WARNINGS.set(())
        try:
            result = original_apply_xray(force_profiles=force_profiles)
            warnings = _WARNINGS.get()
        finally:
            _WARNINGS.reset(warnings_token)
            _CAPTURE_WARNINGS.reset(capture_token)

        if not warnings:
            return result
        return client_runtime.EngineResult(
            result.engine,
            result.ok,
            result.message + "; Предупреждение: " + " | ".join(warnings),
            result.clients,
        )

    client_runtime._deployment_rows = deployment_rows
    client_runtime._apply_xray = apply_xray
    client_runtime._sg_xray_stale_profile_patch_installed = True
