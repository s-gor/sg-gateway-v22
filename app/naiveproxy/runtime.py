from __future__ import annotations

import json
import os
import re
import secrets
import socket
import subprocess
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from urllib.parse import quote

DEFAULT_PORT = 8447
DEFAULT_SERVICE = "sg-gateway-naiveproxy.service"
DEFAULT_STATE_DIR = Path("/var/lib/sg-gateway/naiveproxy")
DEFAULT_CONFIG_DIR = Path("/etc/sg-gateway/naiveproxy")
DEFAULT_BINARY = Path("/opt/sg-gateway/naiveproxy/bin/caddy")
DEFAULT_CERTIFICATE = Path("/etc/letsencrypt/live/{domain}/fullchain.pem")
DEFAULT_PRIVATE_KEY = Path("/etc/letsencrypt/live/{domain}/privkey.pem")
DOMAIN_RE = re.compile(
    r"^(?=.{4,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$"
)
USERNAME_RE = re.compile(r"^[A-Za-z0-9_.-]{1,64}$")
PASSWORD_RE = re.compile(r"^[A-Za-z0-9._~-]{16,256}$")


class NaiveProxyError(RuntimeError):
    pass


@dataclass(frozen=True)
class NaiveProxyUser:
    username: str
    password: str
    enabled: bool = True
    client_id: str = ""


@dataclass(frozen=True)
class NaiveProxySettings:
    domain: str
    port: int = DEFAULT_PORT
    certificate_path: str = ""
    private_key_path: str = ""
    site_root: str = "/var/lib/sg-gateway/naiveproxy/site"

    def normalized(self) -> "NaiveProxySettings":
        domain = normalize_domain(self.domain)
        port = validate_port(self.port)
        certificate = self.certificate_path or str(DEFAULT_CERTIFICATE).format(domain=domain)
        private_key = self.private_key_path or str(DEFAULT_PRIVATE_KEY).format(domain=domain)
        return NaiveProxySettings(
            domain=domain,
            port=port,
            certificate_path=certificate,
            private_key_path=private_key,
            site_root=str(Path(self.site_root)),
        )


def normalize_domain(value: str) -> str:
    domain = str(value or "").strip().lower().rstrip(".")
    if domain.startswith(("http://", "https://")) or not DOMAIN_RE.fullmatch(domain):
        raise NaiveProxyError("Некорректный домен NaiveProxy")
    return domain


def validate_port(port: int | str, reserved: dict[int, str] | None = None) -> int:
    try:
        value = int(port)
    except (TypeError, ValueError) as exc:
        raise NaiveProxyError("Порт NaiveProxy должен быть числом") from exc
    if not 1 <= value <= 65535:
        raise NaiveProxyError("Порт NaiveProxy должен быть в диапазоне 1–65535")
    conflict = (reserved or {}).get(value)
    if conflict:
        raise NaiveProxyError(f"Порт {value} уже занят SG-Gateway: {conflict}")
    return value


def assert_bind_available(port: int, host: str = "0.0.0.0") -> None:
    value = validate_port(port)
    family = socket.AF_INET6 if ":" in host else socket.AF_INET
    with socket.socket(family, socket.SOCK_STREAM) as probe:
        probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            probe.bind((host, value))
        except OSError as exc:
            raise NaiveProxyError(f"TCP-порт {value} недоступен: {exc}") from exc


def _validate_user(user: NaiveProxyUser) -> NaiveProxyUser:
    username = str(user.username or "").strip()
    password = str(user.password or "")
    if not USERNAME_RE.fullmatch(username):
        raise NaiveProxyError("Логин NaiveProxy содержит недопустимые символы")
    if not PASSWORD_RE.fullmatch(password):
        raise NaiveProxyError(
            "Пароль NaiveProxy должен содержать 16–256 безопасных символов"
        )
    return NaiveProxyUser(
        username=username,
        password=password,
        enabled=bool(user.enabled),
        client_id=str(user.client_id or ""),
    )


def generate_user(prefix: str = "sg", client_id: str = "") -> NaiveProxyUser:
    clean_prefix = re.sub(r"[^A-Za-z0-9_.-]", "-", prefix).strip("-") or "sg"
    return NaiveProxyUser(
        username=f"{clean_prefix}-{secrets.token_hex(5)}",
        password=secrets.token_urlsafe(32),
        client_id=str(client_id or ""),
    )


def render_caddyfile(settings: NaiveProxySettings, users: list[NaiveProxyUser]) -> str:
    current = settings.normalized()
    active = [_validate_user(user) for user in users if user.enabled]
    auth = "\n".join(
        f"        basic_auth {user.username} {user.password}" for user in active
    )
    # Explicit high-port listener and explicit SG-Gateway certificate avoid any
    # attempt by this Caddy instance to claim ports 80/443 or run ACME itself.
    order_line = "    order forward_proxy before file_server\n" if active else ""
    proxy_block = (
        "    forward_proxy {\n"
        + auth
        + "\n        hide_ip\n        hide_via\n        probe_resistance\n    }\n"
        if active
        else ""
    )
    return f"""{{
    admin off
    auto_https disable_redirects
{order_line}    log {{
        exclude http.log.error
    }}
}}

:{current.port}, {current.domain}:{current.port} {{
    tls {current.certificate_path} {current.private_key_path}
    encode gzip zstd
{proxy_block}    file_server {{
        root {current.site_root}
    }}
}}
"""


def build_client_uri(settings: NaiveProxySettings, user: NaiveProxyUser, label: str = "") -> str:
    current = settings.normalized()
    account = _validate_user(user)
    if not account.enabled:
        return ""
    fragment = quote(label.strip(), safe="") if label.strip() else ""
    suffix = f"#{fragment}" if fragment else ""
    return (
        f"naive+https://{quote(account.username, safe='')}:{quote(account.password, safe='')}"
        f"@{current.domain}:{current.port}{suffix}"
    )


def redact(value: str) -> str:
    text = str(value)
    text = re.sub(r"(basic_auth\s+\S+\s+)\S+", r"\1***", text)
    text = re.sub(r"(naive\+https://[^:]+:)[^@]+", r"\1***", text)
    return text


def atomic_write(path: Path, content: str, mode: int = 0o600) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, raw = tempfile.mkstemp(prefix=path.name + ".", dir=str(path.parent))
    temporary = Path(raw)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, mode)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def write_runtime(
    settings: NaiveProxySettings,
    users: list[NaiveProxyUser],
    *,
    config_dir: Path = DEFAULT_CONFIG_DIR,
    state_dir: Path = DEFAULT_STATE_DIR,
) -> dict:
    current = settings.normalized()
    caddyfile = render_caddyfile(current, users)
    caddy_path = config_dir / "Caddyfile"
    state_path = state_dir / "state.json"
    if caddy_path.is_file():
        atomic_write(config_dir / "Caddyfile.previous", caddy_path.read_text(encoding="utf-8"), 0o600)
    if state_path.is_file():
        atomic_write(state_dir / "state.json.previous", state_path.read_text(encoding="utf-8"), 0o600)
    atomic_write(caddy_path, caddyfile, 0o640)
    state = {
        "version": 1,
        "settings": asdict(current),
        "users": [asdict(_validate_user(user)) for user in users],
    }
    atomic_write(state_path, json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True) + "\n", 0o600)
    return state


def validate_runtime(
    *,
    binary: Path = DEFAULT_BINARY,
    config_path: Path = DEFAULT_CONFIG_DIR / "Caddyfile",
) -> None:
    if not binary.is_file() or not os.access(binary, os.X_OK):
        raise NaiveProxyError(f"Не найден runtime NaiveProxy: {binary}")
    if not config_path.is_file():
        raise NaiveProxyError(f"Не найден конфиг NaiveProxy: {config_path}")
    result = subprocess.run(
        [str(binary), "validate", "--config", str(config_path), "--adapter", "caddyfile"],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    if result.returncode != 0:
        message = redact((result.stderr or result.stdout).strip())
        raise NaiveProxyError(message or "Caddy отклонил конфигурацию NaiveProxy")
