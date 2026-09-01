from __future__ import annotations

import json
import os
import re
import shutil
import sqlite3
import subprocess
import tempfile
from pathlib import Path

DB_PATH = Path("/var/lib/sg-gateway/sg-gateway.sqlite")
CONFIG_DIR = Path("/etc/sg-gateway/naiveproxy")
CONFIG_PATH = CONFIG_DIR / "Caddyfile"
STATE_DIR = Path("/var/lib/sg-gateway/naiveproxy")
STATE_PATH = STATE_DIR / "state.json"
TLS_DIR = CONFIG_DIR / "tls"
TLS_CERTIFICATE = TLS_DIR / "fullchain.pem"
TLS_PRIVATE_KEY = TLS_DIR / "privkey.pem"
BINARY = Path("/opt/sg-gateway/naiveproxy/bin/caddy")
SERVICE = "sg-gateway-naiveproxy.service"
DEFAULT_PORT = 8447


def _atomic_write(path: Path, content: str, mode: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, raw = tempfile.mkstemp(prefix=path.name + ".", dir=str(path.parent))
    temporary = Path(raw)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, mode)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _redact(text: str) -> str:
    return re.sub(r"(basic_auth\s+\S+\s+)\S+", r"\1***", str(text))


def _load() -> tuple[dict, list[dict], list[int]]:
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    try:
        setting = connection.execute(
            "SELECT host, port, config_json FROM connection_settings WHERE engine = 'naiveproxy'"
        ).fetchone()
        if setting is None:
            raise RuntimeError("NaiveProxy connection settings are missing")
        config = json.loads(setting["config_json"] or "{}")
        settings = {
            "domain": str(setting["host"] or config.get("domain") or "").strip(),
            "port": int(setting["port"] or DEFAULT_PORT),
            "certificate_path": str(config.get("certificate_path") or ""),
            "private_key_path": str(config.get("private_key_path") or ""),
        }
        rows = connection.execute(
            """
            SELECT dc.id, dc.config_json, c.enabled AS client_enabled,
                   d.enabled AS device_enabled
            FROM device_credentials dc
            JOIN devices d ON d.id = dc.device_id
            JOIN clients c ON c.id = d.client_id
            WHERE dc.engine = 'naiveproxy'
            ORDER BY dc.id
            """
        ).fetchall()
        users: list[dict] = []
        credential_ids: list[int] = []
        for row in rows:
            credential_ids.append(int(row["id"]))
            payload = json.loads(row["config_json"] or "{}")
            if not bool(row["client_enabled"]) or not bool(row["device_enabled"]):
                continue
            username = str(payload.get("username") or "").strip()
            password = str(payload.get("password") or "")
            if username and len(password) >= 16:
                users.append({"username": username, "password": password})
        return settings, users, credential_ids
    finally:
        connection.close()


def _reserved_ports() -> dict[int, str]:
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    result: dict[int, str] = {}
    try:
        rows = connection.execute(
            "SELECT engine, port, config_json FROM connection_settings WHERE engine != 'naiveproxy'"
        ).fetchall()
        for row in rows:
            engine = str(row["engine"])
            try:
                result[int(row["port"])] = engine
            except (TypeError, ValueError):
                pass
            try:
                config = json.loads(row["config_json"] or "{}")
            except (TypeError, ValueError, json.JSONDecodeError):
                config = {}
            if isinstance(config, dict):
                for key, value in config.items():
                    if str(key).endswith("_port"):
                        try:
                            result[int(value)] = f"{engine}.{key}"
                        except (TypeError, ValueError):
                            pass
    finally:
        connection.close()
    return result


def _validate(settings: dict) -> None:
    domain = settings["domain"]
    port = int(settings["port"])
    if not domain or not 1 <= port <= 65535:
        raise RuntimeError("NaiveProxy domain/port is invalid")
    conflict = _reserved_ports().get(port)
    if conflict:
        raise RuntimeError(f"TCP port {port} conflicts with {conflict}")
    certificate = Path(settings["certificate_path"] or f"/etc/letsencrypt/live/{domain}/fullchain.pem")
    private_key = Path(settings["private_key_path"] or f"/etc/letsencrypt/live/{domain}/privkey.pem")
    if not certificate.is_file() or not private_key.is_file():
        raise RuntimeError("NaiveProxy TLS certificate is not ready")
    settings["source_certificate_path"] = str(certificate)
    settings["source_private_key_path"] = str(private_key)
    settings["certificate_path"] = str(TLS_CERTIFICATE)
    settings["private_key_path"] = str(TLS_PRIVATE_KEY)
    if not BINARY.is_file() or not os.access(BINARY, os.X_OK):
        raise RuntimeError("NaiveProxy runtime is not installed")


def _render(settings: dict, users: list[dict]) -> str:
    auth = "\n".join(
        f"        basic_auth {item['username']} {item['password']}" for item in users
    )
    order = "    order forward_proxy before file_server\n" if users else ""
    proxy = (
        "    forward_proxy {\n" + auth
        + "\n        hide_ip\n        hide_via\n        probe_resistance\n    }\n"
        if users else ""
    )
    return f"""{{
    admin off
    auto_https disable_redirects
{order}    log {{
        exclude http.log.error
    }}
}}

:{settings['port']}, {settings['domain']}:{settings['port']} {{
    tls {settings['certificate_path']} {settings['private_key_path']}
    encode gzip zstd
{proxy}    file_server {{
        root /var/lib/sg-gateway/naiveproxy/site
    }}
}}
"""


def _run(command: list[str], timeout: int = 30) -> subprocess.CompletedProcess:
    return subprocess.run(command, capture_output=True, text=True, timeout=timeout, check=False)


def sync() -> dict:
    settings, users, credential_ids = _load()
    _validate(settings)
    candidate = _render(settings, users)
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    TLS_DIR.mkdir(parents=True, exist_ok=True)
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    shutil.copy2(settings["source_certificate_path"], TLS_CERTIFICATE)
    shutil.copy2(settings["source_private_key_path"], TLS_PRIVATE_KEY)
    os.chmod(TLS_CERTIFICATE, 0o644)
    os.chmod(TLS_PRIVATE_KEY, 0o640)
    try:
        shutil.chown(TLS_CERTIFICATE, user="root", group="sg-naiveproxy")
        shutil.chown(TLS_PRIVATE_KEY, user="root", group="sg-naiveproxy")
    except LookupError:
        pass
    candidate_path = CONFIG_DIR / "Caddyfile.candidate"
    _atomic_write(candidate_path, candidate, 0o640)
    result = _run([str(BINARY), "validate", "--config", str(candidate_path), "--adapter", "caddyfile"])
    if result.returncode != 0:
        candidate_path.unlink(missing_ok=True)
        raise RuntimeError(_redact(result.stderr or result.stdout or "Caddy validation failed"))
    if CONFIG_PATH.is_file():
        shutil.copy2(CONFIG_PATH, CONFIG_DIR / "Caddyfile.previous")
    if STATE_PATH.is_file():
        shutil.copy2(STATE_PATH, STATE_DIR / "state.json.previous")
    os.replace(candidate_path, CONFIG_PATH)
    os.chmod(CONFIG_PATH, 0o640)
    try:
        shutil.chown(CONFIG_PATH, user="root", group="sg-naiveproxy")
    except LookupError:
        pass
    safe_state = {"version": 1, "settings": settings, "users": len(users)}
    _atomic_write(STATE_PATH, json.dumps(safe_state, ensure_ascii=False, indent=2, sort_keys=True) + "\n", 0o600)
    service = _run(["systemctl", "enable", "--now", SERVICE], timeout=60)
    if service.returncode != 0:
        previous_config = CONFIG_DIR / "Caddyfile.previous"
        previous_state = STATE_DIR / "state.json.previous"
        if previous_config.is_file() and previous_state.is_file():
            rollback(restart=False)
        else:
            CONFIG_PATH.unlink(missing_ok=True)
            STATE_PATH.unlink(missing_ok=True)
        raise RuntimeError(_redact(service.stderr or service.stdout or "NaiveProxy restart failed"))
    if credential_ids:
        connection = sqlite3.connect(DB_PATH)
        try:
            connection.executemany(
                "UPDATE device_credentials SET status = 'applied' WHERE id = ?",
                [(item,) for item in credential_ids],
            )
            connection.commit()
        finally:
            connection.close()
    return {"ok": True, "service": SERVICE, "port": settings["port"], "users": len(users)}


def rollback(restart: bool = True) -> dict:
    previous_config = CONFIG_DIR / "Caddyfile.previous"
    previous_state = STATE_DIR / "state.json.previous"
    if not previous_config.is_file() or not previous_state.is_file():
        raise RuntimeError("No complete NaiveProxy rollback snapshot")
    shutil.copy2(previous_config, CONFIG_PATH)
    shutil.copy2(previous_state, STATE_PATH)
    if restart:
        result = _run(["systemctl", "restart", SERVICE], timeout=60)
        if result.returncode != 0:
            raise RuntimeError(_redact(result.stderr or result.stdout or "NaiveProxy rollback restart failed"))
    return {"ok": True, "service": SERVICE, "rolled_back": True}


def status() -> dict:
    result = _run(["systemctl", "is-active", SERVICE], timeout=10)
    state = {}
    try:
        state = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError):
        pass
    return {
        "ok": result.returncode == 0,
        "service": SERVICE,
        "active": result.returncode == 0,
        "port": (state.get("settings") or {}).get("port", DEFAULT_PORT),
        "users": int(state.get("users") or 0),
    }
