from __future__ import annotations

import json
import uuid


RETIRED_ENGINES = frozenset({"amneziawg", "amneziawg3"})


def install(client_runtime, awg3_runtime, runtime_contracts) -> None:
    """Remove AWG2/AWG3 from active runtime reconciliation.

    Legacy credentials are intentionally left untouched in the database so old
    Clients & Keys backups remain readable. They are no longer prerequisites,
    no longer applied, and no longer allowed to fail Client Apply.
    """

    if getattr(client_runtime, "_retired_awg_runtime_installed", False):
        return

    runtime_contracts.DEFAULT_SPECS = {
        engine: spec
        for engine, spec in runtime_contracts.DEFAULT_SPECS.items()
        if engine not in RETIRED_ENGINES
    }

    def retired_result(engine: str, title: str):
        return client_runtime.EngineResult(
            engine=engine,
            ok=True,
            message=f"{title}: retired; legacy credentials ignored",
            clients=0,
        )

    def repair_active_deployment_configs() -> None:
        """Repair only active Xray credentials.

        The historical implementation also repaired AWG2 credentials and
        therefore required AWG2 server secrets/tools even when AWG2 had been
        retired. Keeping those legacy credentials in the database must not make
        xray.apply depend on the removed AWG2 runtime.
        """

        secrets = client_runtime._read_env(client_runtime.ENGINE_SECRETS)
        runtime = client_runtime._read_env(client_runtime.RUNTIME_ENV)
        public_address = runtime.get("SG_GATEWAY_PUBLIC_ADDRESS", "").strip()
        xray_public = secrets.get("SG_GATEWAY_XRAY_PUBLIC_KEY", "").strip()
        xray_short_id = secrets.get("SG_GATEWAY_XRAY_SHORT_ID", "").strip()
        xray_settings = client_runtime.get_connection_settings("xray")
        vless_encryption = (
            secrets.get("SG_GATEWAY_VLESS_ENCRYPTION", "").strip()
            or str(xray_settings.config.get("vless_encryption") or "").strip()
        )

        with client_runtime.connect() as connection:
            rows = connection.execute(
                """
                SELECT
                    d.id AS client_id,
                    CASE WHEN d.is_primary = 1 THEN c.name
                         ELSE c.name || ' · ' || d.name END AS client_name,
                    dc.engine,
                    dc.engine_object_id,
                    dc.config_json
                FROM devices d
                JOIN clients c ON c.id = d.client_id
                JOIN device_credentials dc ON dc.device_id = d.id
                WHERE dc.engine = 'xray'
                ORDER BY d.id, dc.engine
                """
            ).fetchall()

            for row in rows:
                client_id = int(row["client_id"])
                config = client_runtime._json(row["config_json"])
                user_id = str(
                    config.get("uuid") or row["engine_object_id"] or ""
                ).strip()
                try:
                    user_id = str(uuid.UUID(user_id))
                except (ValueError, AttributeError):
                    user_id = str(uuid.uuid4())

                config.update(
                    {
                        "client_name": str(row["client_name"]),
                        "uuid": user_id,
                        "hysteria_auth": str(
                            config.get("hysteria_auth") or user_id
                        ),
                        "host": xray_settings.host or public_address,
                        "port": int(xray_settings.port),
                        "security": "reality",
                        "type": "tcp",
                        "flow": xray_settings.config.get(
                            "flow", "xtls-rprx-vision"
                        ),
                        "fingerprint": xray_settings.config.get(
                            "fingerprint", "firefox"
                        ),
                        "server_name": xray_settings.config.get(
                            "server_name",
                            runtime.get("SG_GATEWAY_REALITY_SNI", "bing.com"),
                        ),
                        "public_key": xray_public
                        or xray_settings.config.get("public_key", ""),
                        "short_id": xray_short_id
                        or xray_settings.config.get("short_id", ""),
                        "vless_encryption": vless_encryption,
                    }
                )
                connection.execute(
                    """
                    UPDATE device_credentials
                    SET engine_object_id = ?, config_json = ?
                    WHERE device_id = ? AND engine = 'xray'
                    """,
                    (
                        user_id,
                        json.dumps(config, ensure_ascii=False, sort_keys=True),
                        client_id,
                    ),
                )

    client_runtime._apply_awg = lambda: retired_result("amneziawg", "AWG2")
    awg3_runtime.apply_awg3 = lambda: retired_result("amneziawg3", "AWG3")
    client_runtime._repair_deployment_configs = repair_active_deployment_configs
    client_runtime._retired_awg_runtime_installed = True
