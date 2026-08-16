from __future__ import annotations

import json
import secrets
import subprocess
import uuid

from app.connections.settings import get_connection_settings
from app.security.tls import overview as tls_overview
from app.xray.profiles import REALITY_TCP_FLOW


ANYTLS_PORT = 9443
TUIC_PORT = 10443
AWG3_AWG = "/opt/sg-gateway/awg3/bin/awg"


def _run(command: list[str], input_text: str | None = None) -> str:
    result = subprocess.run(
        command,
        input=input_text,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(
            (result.stderr or result.stdout).strip()
            or f"Команда завершилась с кодом {result.returncode}"
        )
    return result.stdout.strip()


def _awg_keypair() -> tuple[str, str]:
    private_key = _run(["awg", "genkey"])
    public_key = _run(["awg", "pubkey"], private_key + "\n")
    return private_key, public_key


def _awg3_keypair() -> tuple[str, str]:
    private_key = _run([AWG3_AWG, "genkey"])
    public_key = _run([AWG3_AWG, "pubkey"], private_key + "\n")
    return private_key, public_key


def _tls_endpoint() -> tuple[str, str]:
    tls = tls_overview()
    domain = str(tls.get("domain") or "").strip()
    if not tls.get("https_ready") or not domain:
        raise RuntimeError("Сначала настройте HTTPS в Security")
    return domain, domain


def build_engine_config(
    engine: str,
    access_id: int,
    access_name: str,
) -> tuple[str, str]:
    if engine == "sgclient":
        payload = {
            "client_name": access_name,
            "format": "base64-links-v2",
            "subscription_token": secrets.token_urlsafe(32),
            "sources": ["xray", "mihomo", "anytls", "tuic"],
        }
        return (
            f"sgclient-{access_id}",
            json.dumps(payload, ensure_ascii=False, sort_keys=True),
        )

    if engine == "amneziawg":
        settings = get_connection_settings(engine)
        private_key, public_key = _awg_keypair()
        payload = {
            "client_name": access_name,
            "private_key": private_key,
            "public_key": public_key,
            "address": f"10.66.{min(254, access_id // 250)}.{2 + (access_id % 250)}/32",
            "dns": settings.config.get("dns", "1.1.1.1"),
            "server_public_key": settings.config.get("server_public_key", ""),
            "endpoint": f"{settings.host}:{settings.port}",
            "allowed_ips": settings.config.get(
                "allowed_ips",
                "0.0.0.0/0, ::/0",
            ),
            "persistent_keepalive": settings.config.get(
                "persistent_keepalive",
                25,
            ),
        }
        return public_key, json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
        )

    if engine == "amneziawg3":
        settings = get_connection_settings(engine)
        private_key, public_key = _awg3_keypair()
        payload = {
            "client_name": access_name,
            "private_key": private_key,
            "public_key": public_key,
            "address": f"10.67.{min(254, access_id // 250)}.{2 + (access_id % 250)}/32",
            "dns": settings.config.get("dns", "1.1.1.1"),
            "server_public_key": settings.config.get("server_public_key", ""),
            "endpoint": f"{settings.host}:{settings.port}",
            "allowed_ips": settings.config.get("allowed_ips", "0.0.0.0/0, ::/0"),
            "persistent_keepalive": settings.config.get("persistent_keepalive", "25-35"),
            "generation": 3,
        }
        return public_key, json.dumps(payload, ensure_ascii=False, sort_keys=True)

    if engine == "xray":
        settings = get_connection_settings(engine)
        user_id = str(uuid.uuid4())
        payload = {
            "client_name": access_name,
            "uuid": user_id,
            "hysteria_auth": secrets.token_urlsafe(24),
            "host": settings.host,
            "port": settings.port,
            "security": settings.config.get("security", "reality"),
            "type": settings.config.get("type", "tcp"),
            "flow": settings.config.get("flow", REALITY_TCP_FLOW),
            "fingerprint": settings.config.get("fingerprint", "firefox"),
            "server_name": settings.config.get("server_name", "bing.com"),
            "public_key": settings.config.get("public_key", ""),
            "short_id": settings.config.get("short_id", ""),
            "vless_encryption": settings.config.get("vless_encryption", ""),
            "profiles": ["reality_tcp", "xhttp_reality"],
        }
        return user_id, json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
        )

    if engine == "mihomo":
        from app.mihomo.service import build_client_credentials

        return build_client_credentials(access_id, access_name)

    if engine == "anytls":
        host, server_name = _tls_endpoint()
        password = secrets.token_urlsafe(28)
        payload = {
            "client_name": access_name,
            "password": password,
            "host": host,
            "port": ANYTLS_PORT,
            "server_name": server_name,
            "fingerprint": "firefox",
        }
        return f"anytls-{access_id}", json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
        )

    if engine == "tuic":
        host, server_name = _tls_endpoint()
        user_id = str(uuid.uuid4())
        password = secrets.token_urlsafe(24)
        payload = {
            "client_name": access_name,
            "uuid": user_id,
            "password": password,
            "host": host,
            "port": TUIC_PORT,
            "server_name": server_name,
            "congestion_control": "bbr",
            "udp_relay_mode": "native",
            "alpn": "h3",
        }
        return user_id, json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
        )

    raise ValueError(f"Неподдерживаемый движок клиента: {engine}")
