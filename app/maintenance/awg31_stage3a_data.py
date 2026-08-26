from __future__ import annotations

import base64
import json
import os
import secrets
import shutil
import sqlite3
import subprocess
from pathlib import Path

from app.connections.awg31 import (
    BOOL_FIELDS,
    DEFAULT_PARAMETERS,
    FIELD_NAMES,
    H_FIELDS,
    I_FIELDS,
    J_FIELDS,
    RANGE_FIELDS,
    REAL31_DEFAULT_PARAMETERS,
    S_FIELDS,
    validate_parameters,
)
from app.maintenance.awg31_stage3a_common import DNS, ENDPOINT, ENGINE_ID, INTERFACE, NETWORK


class DataMixin:
    @staticmethod
    def _x25519_public(private: bytes) -> bytes:
        scalar = int.from_bytes(private, "little")
        prime = 2**255 - 19
        x1, x2, z2, x3, z3, swap = 9, 1, 0, 9, 1, 0
        for bit in range(254, -1, -1):
            current = (scalar >> bit) & 1
            swap ^= current
            if swap:
                x2, x3 = x3, x2
                z2, z3 = z3, z2
            swap = current
            a = (x2 + z2) % prime
            aa = a * a % prime
            b = (x2 - z2) % prime
            bb = b * b % prime
            e = (aa - bb) % prime
            c = (x3 + z3) % prime
            d = (x3 - z3) % prime
            da = d * a % prime
            cb = c * b % prime
            x3 = (da + cb) ** 2 % prime
            z3 = x1 * (da - cb) ** 2 % prime
            x2 = aa * bb % prime
            z2 = e * (aa + 121665 * e) % prime
        if swap:
            x2, x3 = x3, x2
            z2, z3 = z3, z2
        return (x2 * pow(z2, prime - 2, prime) % prime).to_bytes(32, "little")

    @classmethod
    def _keypair(cls) -> tuple[str, str]:
        raw = bytearray(secrets.token_bytes(32))
        raw[0] &= 248
        raw[31] &= 127
        raw[31] |= 64
        private = bytes(raw)
        return (
            base64.b64encode(private).decode("ascii"),
            base64.b64encode(cls._x25519_public(private)).decode("ascii"),
        )

    @staticmethod
    def _raw_settings(connection: sqlite3.Connection) -> dict[str, object]:
        row = connection.execute(
            "SELECT config_json FROM connection_settings WHERE engine = ?", (ENGINE_ID,)
        ).fetchone()
        if row is None:
            return {}
        try:
            raw = json.loads(row[0] or "{}")
        except (TypeError, ValueError, json.JSONDecodeError):
            return {}
        return raw if isinstance(raw, dict) else {}

    @classmethod
    def _settings(cls, connection: sqlite3.Connection) -> dict[str, str | int]:
        raw = cls._raw_settings(connection)
        values = {
            name: raw.get(name, raw.get(name.lower(), DEFAULT_PARAMETERS[name]))
            for name in FIELD_NAMES
        }
        lower_keys = {str(name).lower() for name in raw}
        missing_real31 = any(
            name.lower() not in lower_keys for name in RANGE_FIELDS + BOOL_FIELDS
        )
        unsafe_padding = False
        for name in S_FIELDS:
            try:
                unsafe_padding = unsafe_padding or int(values[name]) < 12
            except (TypeError, ValueError):
                unsafe_padding = True
        if missing_real31 or unsafe_padding:
            for name in J_FIELDS + S_FIELDS + H_FIELDS + RANGE_FIELDS + BOOL_FIELDS:
                values[name] = REAL31_DEFAULT_PARAMETERS[name]
        return validate_parameters(values)

    @staticmethod
    def _valid_header_key(value: object) -> str:
        text = str(value or "").strip()
        if not text:
            return ""
        try:
            decoded = base64.b64decode(text, validate=True)
        except (ValueError, TypeError):
            return ""
        return text if len(decoded) == 32 else ""

    @classmethod
    def _header_protection_key(cls, connection: sqlite3.Connection) -> str:
        raw = cls._raw_settings(connection)
        key = cls._valid_header_key(raw.get("header_protection_key"))
        if key:
            return key
        rows = connection.execute(
            "SELECT config_json FROM device_credentials WHERE engine = ? ORDER BY id",
            (ENGINE_ID,),
        ).fetchall()
        for row in rows:
            try:
                payload = json.loads(row[0] or "{}")
            except (TypeError, ValueError, json.JSONDecodeError):
                continue
            if isinstance(payload, dict):
                key = cls._valid_header_key(payload.get("header_protection_key"))
                if key:
                    return key
        return base64.b64encode(secrets.token_bytes(32)).decode("ascii")

    @staticmethod
    def _persist_settings(
        connection: sqlite3.Connection,
        settings: dict[str, str | int],
        server_public_key: str,
        header_protection_key: str,
    ) -> None:
        row = connection.execute(
            "SELECT config_json FROM connection_settings WHERE engine = ?", (ENGINE_ID,)
        ).fetchone()
        payload: dict[str, object] = {}
        if row is not None:
            try:
                raw = json.loads(row[0] or "{}")
            except (TypeError, ValueError, json.JSONDecodeError):
                raw = {}
            if isinstance(raw, dict):
                payload = raw
        payload.update(
            {
                "profile": "awg31",
                "generation": 31,
                "dns": DNS,
                "transport": "udp",
                "endpoint": ENDPOINT,
                "allowed_ips": "0.0.0.0/0",
                "server_public_key": server_public_key,
                "header_protection_key": header_protection_key,
                **{name.lower(): value for name, value in settings.items()},
            }
        )
        serialized = json.dumps(payload, sort_keys=True)
        if row is None:
            connection.execute(
                """
                INSERT INTO connection_settings(engine, enabled, host, port, config_json)
                VALUES (?, 1, 'awg31.internal', 587, ?)
                """,
                (ENGINE_ID, serialized),
            )
            return
        connection.execute(
            """
            UPDATE connection_settings
            SET enabled = 1, host = 'awg31.internal', port = 587, config_json = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE engine = ?
            """,
            (serialized, ENGINE_ID),
        )

    @classmethod
    def _sync_credentials(
        cls,
        connection: sqlite3.Connection,
        settings: dict[str, str | int],
        server_public_key: str,
        header_protection_key: str,
    ) -> int:
        rows = connection.execute(
            """
            SELECT d.id, d.name, d.is_primary, c.name
            FROM devices d JOIN clients c ON c.id = d.client_id
            ORDER BY d.id
            """
        ).fetchall()
        created = 0
        shared = {
            "profile": "awg31",
            "engine": ENGINE_ID,
            "dns": DNS,
            "endpoint": ENDPOINT,
            "transport": "udp",
            "interface": INTERFACE,
            "network": NETWORK,
            "allowed_ips": "0.0.0.0/0",
            "persistent_keepalive": 25,
            "generation": 31,
            "server_public_key": server_public_key,
            "header_protection_key": header_protection_key,
            **{name.lower(): value for name, value in settings.items()},
        }
        for device_id, device_name, is_primary, client_name in rows:
            label = client_name if is_primary else f"{client_name} · {device_name}"
            existing = connection.execute(
                "SELECT id, config_json FROM device_credentials "
                "WHERE device_id = ? AND engine = ?",
                (device_id, ENGINE_ID),
            ).fetchone()
            if existing is None:
                private_key, public_key = cls._keypair()
                payload = {
                    **shared,
                    "client_name": label,
                    "private_key": private_key,
                    "public_key": public_key,
                    "address": f"10.131.0.{2 + ((int(device_id) - 1) % 253)}/32",
                }
                connection.execute(
                    """
                    INSERT INTO device_credentials(device_id, engine, status, engine_object_id, config_json)
                    VALUES (?, ?, 'pending', ?, ?)
                    """,
                    (device_id, ENGINE_ID, public_key, json.dumps(payload, sort_keys=True)),
                )
                created += 1
                continue

            credential_id, config_json = existing
            try:
                raw_payload = json.loads(config_json or "{}")
            except (TypeError, ValueError, json.JSONDecodeError):
                raw_payload = {}
            if not isinstance(raw_payload, dict):
                raw_payload = {}
            payload = dict(raw_payload)
            payload.update(shared)
            payload["client_name"] = label
            if payload != raw_payload:
                connection.execute(
                    "UPDATE device_credentials SET config_json = ?, status = 'pending' WHERE id = ?",
                    (json.dumps(payload, sort_keys=True), int(credential_id)),
                )
        return created

    @staticmethod
    def _parameter_lines(
        settings: dict[str, str | int], header_protection_key: str
    ) -> list[str]:
        lines: list[str] = []
        for name in I_FIELDS + J_FIELDS + S_FIELDS + H_FIELDS:
            value = settings[name]
            if name in I_FIELDS and value == "":
                continue
            lines.append(f"{name} = {value}")
        lines.append(f"HeaderProtectionKey = {header_protection_key}")
        for name in RANGE_FIELDS + BOOL_FIELDS:
            lines.append(f"{name} = {settings[name]}")
        return lines

    def _prepare_state(self, work: Path, runtime: Path) -> tuple[Path, str, str]:
        state = work / "awg31-state"
        if self.layout.state.is_dir():
            shutil.copytree(self.layout.state, state)
        else:
            state.mkdir()
        private_path = state / "server-private.key"
        public_path = state / "server-public.key"
        if private_path.is_file() and public_path.is_file():
            return state, private_path.read_text().strip(), public_path.read_text().strip()
        awg = runtime / "bin/awg"
        private = subprocess.run(
            [str(awg), "genkey"], text=True, capture_output=True, check=True
        ).stdout.strip()
        public = subprocess.run(
            [str(awg), "pubkey"], input=private + "\n", text=True, capture_output=True, check=True
        ).stdout.strip()
        private_path.write_text(private + "\n", encoding="utf-8")
        public_path.write_text(public + "\n", encoding="utf-8")
        os.chmod(private_path, 0o600)
        os.chmod(public_path, 0o644)
        return state, private, public

    def _render_configs(
        self,
        *,
        work: Path,
        connection: sqlite3.Connection,
        settings: dict[str, str | int],
        header_protection_key: str,
        server_private: str,
        server_public: str,
    ) -> tuple[Path, int]:
        config = work / "awg31-config"
        peers = config / "peers"
        peers.mkdir(parents=True)
        peer_blocks: list[str] = []
        rows = connection.execute(
            "SELECT device_id, config_json FROM device_credentials WHERE engine = ? ORDER BY device_id",
            (ENGINE_ID,),
        ).fetchall()
        for device_id, config_json in rows:
            payload = json.loads(config_json or "{}")
            if not isinstance(payload, dict):
                raise TypeError(f"invalid AWG31 credential for device {device_id}")
            private_key = str(payload.get("private_key") or "")
            public_key = str(payload.get("public_key") or "")
            address = str(payload.get("address") or "")
            if not private_key or not public_key or not address:
                raise RuntimeError(f"incomplete AWG31 credential for device {device_id}")
            body = "\n".join(
                [
                    "[Interface]",
                    f"PrivateKey = {private_key}",
                    f"Address = {address}",
                    f"DNS = {DNS}",
                    *self._parameter_lines(settings, header_protection_key),
                    "",
                    "[Peer]",
                    f"PublicKey = {server_public}",
                    f"Endpoint = {ENDPOINT}",
                    "AllowedIPs = 0.0.0.0/0",
                    "PersistentKeepalive = 25",
                    "",
                ]
            )
            peer_path = peers / f"device-{device_id}.conf"
            peer_path.write_text(body, encoding="utf-8")
            os.chmod(peer_path, 0o600)
            peer_blocks.extend(
                ["[Peer]", f"PublicKey = {public_key}", f"AllowedIPs = {address}", ""]
            )
        server_body = "\n".join(
            [
                "[Interface]",
                f"PrivateKey = {server_private}",
                "ListenPort = 587",
                "Address = 10.131.0.1/24",
                *self._parameter_lines(settings, header_protection_key),
                *peer_blocks,
            ]
        ).rstrip() + "\n"
        server_path = config / "awg31.conf"
        server_path.write_text(server_body, encoding="utf-8")
        os.chmod(server_path, 0o600)
        return config, len(rows)
