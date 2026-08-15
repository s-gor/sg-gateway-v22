from __future__ import annotations

import json
import os
import re
import socket
import subprocess
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path

from app.config import load_config
from app.hostd.client import run_hostd_command
from app.maintenance.operations import log_operation


DOMAIN_RE = re.compile(
    r"^(?=.{4,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$"
)


class TlsError(RuntimeError):
    pass


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _state_dir() -> Path:
    override = os.getenv("SG_GATEWAY_SECURITY_STATE_DIR", "").strip()
    return Path(override) if override else load_config().data_dir / "security"


def _request_path() -> Path:
    return _state_dir() / "tls-request.json"


def _state_path() -> Path:
    return _state_dir() / "tls-state.json"


def _backups_dir() -> Path:
    return _state_dir() / "backups"


def _ensure_dirs() -> None:
    _state_dir().mkdir(parents=True, exist_ok=True)
    _backups_dir().mkdir(parents=True, exist_ok=True)


def normalize_domain(value: str) -> str:
    domain = (value or "").strip().lower().rstrip(".")
    if domain.startswith("http://") or domain.startswith("https://"):
        raise TlsError("Введите только домен без http:// или https://")
    if not DOMAIN_RE.fullmatch(domain):
        raise TlsError("Некорректное доменное имя")
    return domain


def normalize_email(value: str) -> str:
    """Legacy compatibility: email is no longer required by SG-Gateway."""
    return (value or "").strip().lower()


def _write_json(path: Path, payload: dict, mode: int = 0o600) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + f".tmp-{uuid.uuid4().hex}")
    with temporary.open("w", encoding="utf-8") as stream:
        json.dump(payload, stream, ensure_ascii=False, indent=2, sort_keys=True)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.chmod(temporary, mode)
    os.replace(temporary, path)


def _read_json(path: Path) -> dict | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def _public_ip() -> str:
    for url in ("https://api.ipify.org", "https://ifconfig.me/ip"):
        try:
            request = urllib.request.Request(
                url,
                headers={"User-Agent": "SG-Gateway-Security/1.0"},
            )
            with urllib.request.urlopen(request, timeout=5) as response:
                value = response.read(128).decode("ascii", "ignore").strip()
            socket.inet_aton(value)
            return value
        except (OSError, ValueError, urllib.error.URLError, TimeoutError):
            continue
    return ""


def check_domain(domain: str) -> dict:
    normalized = normalize_domain(domain)
    addresses: set[str] = set()
    try:
        for item in socket.getaddrinfo(normalized, 443, type=socket.SOCK_STREAM):
            address = item[4][0]
            if ":" not in address:
                addresses.add(address)
    except socket.gaierror as exc:
        return {
            "domain": normalized,
            "ok": False,
            "status": "error",
            "message": f"DNS не разрешается: {exc}",
            "addresses": [],
            "public_ip": _public_ip(),
            "matches_public_ip": False,
            "checked_at": _utc_now(),
        }

    public_ip = _public_ip()
    matches = bool(public_ip and public_ip in addresses)
    if not addresses:
        status = "error"
        message = "Для домена не найден IPv4-адрес"
    elif public_ip and not matches:
        status = "warning"
        message = (
            f"Домен ведёт на {', '.join(sorted(addresses))}, "
            f"а публичный IPv4 сервера определён как {public_ip}"
        )
    elif matches:
        status = "ok"
        message = "DNS домена указывает на публичный IPv4 этого сервера"
    else:
        status = "warning"
        message = "DNS найден, но публичный IPv4 сервера определить не удалось"

    return {
        "domain": normalized,
        "ok": status != "error",
        "status": status,
        "message": message,
        "addresses": sorted(addresses),
        "public_ip": public_ip,
        "matches_public_ip": matches,
        "checked_at": _utc_now(),
    }


def stage_request(domain: str, email: str | None = None) -> dict:
    _ensure_dirs()
    normalized_domain = normalize_domain(domain)
    dns = check_domain(normalized_domain)
    config = load_config()
    payload = {
        "domain": normalized_domain,
        "panel_port": int(config.public_port),
        "public_port": int(config.public_port),
        "backend_port": int(config.port),
        "dns": dns,
        "created_at": _utc_now(),
    }
    _write_json(_request_path(), payload)
    log_operation(
        "security.tls.check",
        f"tls:{normalized_domain}",
        dns["message"],
        status="ok" if dns["status"] != "error" else "error",
    )
    return payload


def _run_hostd(action: str, timeout: float) -> dict:
    command = f"tls.{action}"
    result = run_hostd_command(command, timeout=timeout)
    if result.status != "ok":
        raise TlsError(result.message or f"{command} failed")
    payload = dict(result.payload)
    payload.setdefault("ok", True)
    payload.setdefault("message", result.message)
    return payload


def issue_certificate() -> dict:
    """Compatibility wrapper. The UI normally starts the live HTTPS job."""
    request = _read_json(_request_path())
    if not request:
        raise TlsError("Сначала проверьте домен")
    result = _run_hostd("issue.start", timeout=20)
    log_operation(
        "security.tls.issue.start",
        f"tls:{request.get('domain', 'unknown')}",
        str(result.get("message", "HTTPS task started")),
    )
    return result


def renew_certificate() -> dict:
    payload = _run_hostd("renew", timeout=600)
    state = _read_json(_state_path()) or {}
    log_operation(
        "security.tls.renew",
        f"tls:{state.get('domain', 'unknown')}",
        str(payload.get("message", "TLS certificate renewed")),
    )
    return payload


def rollback_latest() -> dict:
    payload = _run_hostd("rollback", timeout=240)
    log_operation(
        "security.tls.rollback",
        "tls:nginx",
        str(payload.get("message", "TLS configuration restored")),
    )
    return payload


def _service_active(name: str) -> bool:
    try:
        result = subprocess.run(
            ["systemctl", "is-active", "--quiet", name],
            capture_output=True,
            text=True,
            timeout=3,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0


def _service_enabled(name: str) -> bool:
    try:
        result = subprocess.run(
            ["systemctl", "is-enabled", "--quiet", name],
            capture_output=True,
            text=True,
            timeout=3,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0


def _safe_is_file(path: Path) -> bool:
    try:
        return path.is_file()
    except OSError:
        return False


def _backup_names() -> list[str]:
    try:
        return [
            item.name
            for item in sorted(_backups_dir().glob("*"), reverse=True)[:10]
            if item.is_dir()
        ]
    except OSError:
        return []


def overview() -> dict:
    _ensure_dirs()
    state = _read_json(_state_path()) or {}
    request = _read_json(_request_path()) or {}
    domain = str(state.get("domain") or request.get("domain") or "")
    certificate = state.get("certificate")
    certificate = certificate if isinstance(certificate, dict) else {}
    config = load_config()
    public_port = int(
        state.get("public_port")
        or request.get("public_port")
        or config.public_port
    )
    backend_port = int(
        state.get("backend_port")
        or request.get("backend_port")
        or config.port
    )
    nginx_conf = Path("/etc/nginx/sites-available/sg-gateway")
    nginx_active = _service_active("nginx.service")
    https_ready = bool(
        domain
        and certificate
        and state.get("https_ready") is not False
        and _safe_is_file(nginx_conf)
        and nginx_active
    )
    dns = request.get("dns") or (check_domain(domain) if domain else None)
    port_suffix = "" if public_port == 443 else f":{public_port}"
    return {
        "domain": domain,
        "https_ready": https_ready,
        "nginx_active": nginx_active,
        "certbot_timer": _service_active("certbot.timer"),
        "certbot_timer_enabled": _service_enabled("certbot.timer"),
        "certificate": certificate,
        "dns": dns,
        "panel_port": public_port,
        "public_port": public_port,
        "backend_port": backend_port,
        "public_url": f"https://{domain}{port_suffix}" if domain else "",
        "nginx_config": str(nginx_conf),
        "certificate_path": str(
            state.get("certificate_path")
            or (f"/etc/letsencrypt/live/{domain}/fullchain.pem" if domain else "")
        ),
        "last_action": str(state.get("last_action") or ""),
        "last_message": str(state.get("last_message") or ""),
        "updated_at": str(state.get("updated_at") or ""),
        "backups": _backup_names(),
    }


def health_status() -> dict:
    state = overview()
    if not state["domain"]:
        return {
            "status": "warning",
            "message": "Домен и HTTPS ещё не настроены",
        }
    if state["https_ready"]:
        days = state["certificate"].get("days_left")
        suffix = f", осталось {days} дней" if days is not None else ""
        return {
            "status": "ok",
            "message": f"HTTPS активен для {state['domain']}{suffix}",
        }
    return {
        "status": "warning",
        "message": f"HTTPS для {state['domain']} ещё не готов",
    }
