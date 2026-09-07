from __future__ import annotations

import subprocess
from dataclasses import dataclass
from typing import Any

from app.connections.settings import get_connection_settings, update_connection_settings
from app.security.tls import overview as tls_overview
from app.xray.encryption import client_value_ready
from app.xray.salamander import (
    GECKO_MINIMUM_VERSION,
    GECKO_MODE,
    SALAMANDER_MINIMUM_VERSION,
    SALAMANDER_MODE,
    SALAMANDER_MODE_NONE,
    SalamanderError,
    ensure_base_has_no_salamander,
    generate_password,
    minimum_version_for_mode,
    normalise_mode,
    password_ready,
    safe_status,
    validate_password,
    version_supported as salamander_version_supported,
)
from app.xray.settings_transactions import (
    SettingsTransaction,
    begin as begin_settings_transaction,
    commit as commit_settings_transaction,
    pending as pending_settings_transaction,
    rollback as rollback_settings_transaction,
)


REALITY_TCP_FLOW = "xtls-rprx-vision"
XRAY_MINIMUM_VERSION = "26.7.28"
# Compatibility name used by older modules; the policy is minimum, not exact.
XRAY_REQUIRED_VERSION = XRAY_MINIMUM_VERSION
XHTTP_MODES = ("auto", "stream-one", "stream-up", "packet-up")
XHTTP_MODE_OPTIONS = (
    {
        "value": "auto",
        "title": "Auto",
        "note": "Xray выбирает режим по текущей схеме транспорта.",
    },
    {
        "value": "stream-one",
        "title": "Stream One",
        "note": "Прямой REALITY/TLS без CDN: меньше накладных расходов.",
    },
    {
        "value": "stream-up",
        "title": "Stream Up",
        "note": "Длительный upload-поток или раздельные upload/download маршруты.",
    },
    {
        "value": "packet-up",
        "title": "Packet Up",
        "note": "Совместимый режим для CDN и прокси с reassembly на сервере.",
    },
)

# Same client fingerprint contract as SG-Panel. Firefox is the default for
# fresh/missing values. An unknown value already stored by an older version is
# preserved and shown by the UI, but new arbitrary values are rejected.
FINGERPRINT_VALUES = (
    "chrome",
    "brave",
    "edge",
    "firefox",
    "safari",
    "ios",
    "android",
    "opera",
    "vivaldi",
    "360",
    "qq",
    "random",
    "randomized",
    "unsafe",
)
FINGERPRINT_DEFAULT = "firefox"
VLESS_ENCRYPTION_PLACEHOLDER = "PLACEHOLDER_VLESS_ENCRYPTION"

# Client-only XHTTP XMUX fast-rotation preset for Russian networks.
# maxConnections stays 0 because Xray forbids a positive maxConnections together
# with a positive maxConcurrency.
XHTTP_XMUX_RF = {
    "maxConcurrency": 5,
    "maxConnections": 0,
    "cMaxReuseTimes": 0,
    "hMaxRequestTimes": "300-600",
    "hMaxReusableSecs": "900-1800",
    "hKeepAlivePeriod": 0,
}


class XrayProfilesError(RuntimeError):
    pass


@dataclass(frozen=True)
class XrayProfile:
    id: str
    title: str
    transport: str
    security: str
    enabled: bool
    port: int
    path: str
    tls_required: bool
    ready: bool
    status: str
    note: str
    flow: str = ""
    encryption_required: bool = False
    encryption_ready: bool = False
    mode: str = ""
    xmux_enabled: bool = False
    xmux: dict[str, Any] | None = None


@dataclass(frozen=True)
class PreparedXraySettings:
    host: str
    port: int
    config: dict[str, Any]
    salamander_changed: bool
    salamander_rotated: bool


def _bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on", "enabled"}


def _port(value: Any, default: int) -> int:
    try:
        port = int(value)
    except (TypeError, ValueError):
        port = default
    if not 1 <= port <= 65535:
        raise XrayProfilesError(f"Некорректный порт: {value}")
    return port


def _path(value: Any, default: str) -> str:
    path = str(value or default).strip()
    if not path.startswith("/"):
        path = "/" + path
    if len(path) > 128 or any(char.isspace() for char in path):
        raise XrayProfilesError("Path должен начинаться с / и не содержать пробелов")
    return path


def _mode(value: Any, default: str) -> str:
    mode = str(value or default).strip().lower()
    if mode not in XHTTP_MODES:
        raise XrayProfilesError(
            "Некорректный XHTTP mode. Допустимы: " + ", ".join(XHTTP_MODES)
        )
    return mode


def _fingerprint(value: Any, default: str = FINGERPRINT_DEFAULT) -> str:
    raw = str(value or "").strip()
    if not raw:
        return default
    normalized = raw.lower()
    return normalized if normalized in FINGERPRINT_VALUES else raw


def _installed_xray_version() -> str:
    for binary in ("/usr/local/bin/xray", "xray"):
        try:
            result = subprocess.run(
                [binary, "version"],
                capture_output=True,
                text=True,
                timeout=4,
                check=False,
            )
        except (OSError, subprocess.SubprocessError):
            continue
        first = (result.stdout or result.stderr or "").splitlines()
        if result.returncode == 0 and first:
            parts = first[0].split()
            if len(parts) >= 2:
                return parts[1].lstrip("v")
    return ""


def _version_key(value: str) -> tuple[int, ...]:
    try:
        return tuple(int(part) for part in str(value or "").lstrip("v").split("."))
    except (TypeError, ValueError):
        return ()


def _version_supported(installed: str) -> bool:
    current = _version_key(installed)
    minimum = _version_key(XRAY_MINIMUM_VERSION)
    if not current or not minimum:
        return False
    width = max(len(current), len(minimum))
    current += (0,) * (width - len(current))
    minimum += (0,) * (width - len(minimum))
    return current >= minimum


def _service_active() -> bool:
    try:
        result = subprocess.run(
            ["systemctl", "is-active", "--quiet", "xray.service"],
            capture_output=True,
            text=True,
            timeout=4,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return result.returncode == 0


def _config() -> tuple[Any, dict[str, Any], dict[str, Any]]:
    settings = get_connection_settings("xray")
    config = dict(settings.config)
    tls = tls_overview()
    return settings, config, tls


def _values(config: dict[str, Any], legacy_port: int) -> dict[str, Any]:
    try:
        obfs_mode = normalise_mode(config.get("hysteria2_obfs_mode"))
    except SalamanderError:
        obfs_mode = SALAMANDER_MODE_NONE
    finalmask = config.get("hysteria2_finalmask")
    if not isinstance(finalmask, dict):
        finalmask = {}
    uri_scheme = str(config.get("hysteria2_uri_scheme") or "hysteria2").strip().lower()
    if uri_scheme not in {"hysteria2", "hy2"}:
        uri_scheme = "hysteria2"
    return {
        "fingerprint": _fingerprint(config.get("fingerprint")),
        "reality_tcp_enabled": _bool(config.get("reality_tcp_enabled"), True),
        "reality_tcp_port": _port(config.get("reality_tcp_port"), legacy_port or 443),
        "xhttp_reality_enabled": _bool(config.get("xhttp_reality_enabled"), True),
        "xhttp_reality_port": _port(config.get("xhttp_reality_port"), 8444),
        "xhttp_reality_path": _path(config.get("xhttp_reality_path"), "/sg-xhttp-reality"),
        "xhttp_reality_mode": _mode(config.get("xhttp_reality_mode"), "stream-one"),
        "xhttp_reality_xmux_enabled": True,
        "xhttp_tls_enabled": _bool(config.get("xhttp_tls_enabled"), False),
        "xhttp_tls_port": _port(config.get("xhttp_tls_port"), 8445),
        "xhttp_tls_path": _path(config.get("xhttp_tls_path"), "/sg-xhttp-tls"),
        "xhttp_tls_mode": _mode(config.get("xhttp_tls_mode"), "auto"),
        "xhttp_tls_xmux_enabled": True,
        "hysteria2_enabled": _bool(config.get("hysteria2_enabled"), False),
        "hysteria2_port": _port(config.get("hysteria2_port"), 8446),
        "hysteria2_obfs_mode": obfs_mode,
        "hysteria2_obfs_password": str(config.get("hysteria2_obfs_password") or ""),
        "hysteria2_finalmask": finalmask,
        "hysteria2_uri_scheme": uri_scheme,
    }


def _vless_encryption_ready(value: Any) -> bool:
    return client_value_ready(value)


def _prepare(form: Any) -> PreparedXraySettings:
    settings, config, tls = _config()
    current = _values(config, int(settings.port or 443))
    tls_ready = bool(tls.get("https_ready"))

    current_fingerprint = str(current["fingerprint"])
    requested_fingerprint = _fingerprint(
        form.get("fingerprint", current_fingerprint), current_fingerprint
    )
    if (
        requested_fingerprint not in FINGERPRINT_VALUES
        and requested_fingerprint != current_fingerprint
    ):
        raise XrayProfilesError(
            "Некорректный Fingerprint. Выберите значение из списка SG-Panel."
        )

    values: dict[str, Any] = {
        "fingerprint": requested_fingerprint,
        "reality_tcp_enabled": bool(form.get("reality_tcp_enabled")),
        "reality_tcp_port": int(current["reality_tcp_port"]),
        "xhttp_reality_enabled": bool(form.get("xhttp_reality_enabled")),
        "xhttp_reality_port": int(current["xhttp_reality_port"]),
        "xhttp_reality_path": _path(form.get("xhttp_reality_path"), "/sg-xhttp-reality"),
        "xhttp_reality_mode": _mode(
            form.get("xhttp_reality_mode"), str(current["xhttp_reality_mode"])
        ),
        "xhttp_reality_xmux_enabled": True,
        "xhttp_tls_enabled": (
            bool(form.get("xhttp_tls_enabled"))
            if tls_ready else bool(current["xhttp_tls_enabled"])
        ),
        "xhttp_tls_port": int(current["xhttp_tls_port"]),
        "xhttp_tls_path": _path(
            form.get("xhttp_tls_path"), str(current["xhttp_tls_path"])
        ),
        "xhttp_tls_mode": _mode(
            form.get("xhttp_tls_mode"), str(current["xhttp_tls_mode"])
        ),
        "xhttp_tls_xmux_enabled": True,
        "hysteria2_enabled": (
            bool(form.get("hysteria2_enabled"))
            if tls_ready else bool(current["hysteria2_enabled"])
        ),
        "hysteria2_port": int(current["hysteria2_port"]),
    }

    if not any(
        values[key]
        for key in (
            "reality_tcp_enabled",
            "xhttp_reality_enabled",
            "xhttp_tls_enabled",
            "hysteria2_enabled",
        )
    ):
        raise XrayProfilesError("Должен оставаться включён хотя бы один Xray-профиль")
    if (values["xhttp_tls_enabled"] or values["hysteria2_enabled"]) and not tls_ready:
        raise XrayProfilesError("Сначала настройте HTTPS в Security")
    if (
        values["xhttp_reality_enabled"] or values["xhttp_tls_enabled"]
    ) and not _vless_encryption_ready(config.get("vless_encryption")):
        raise XrayProfilesError(
            "VLESS Encryption не готов. Повторите установку текущей версии SG-Gateway."
        )

    tcp_ports = []
    for enabled_key, port_key in (
        ("reality_tcp_enabled", "reality_tcp_port"),
        ("xhttp_reality_enabled", "xhttp_reality_port"),
        ("xhttp_tls_enabled", "xhttp_tls_port"),
    ):
        if values[enabled_key]:
            tcp_ports.append(values[port_key])
    if len(tcp_ports) != len(set(tcp_ports)):
        raise XrayProfilesError("Включённые TCP-профили должны использовать разные порты")

    try:
        requested_obfs = normalise_mode(
            form.get("hysteria2_obfs_mode", current["hysteria2_obfs_mode"])
        )
        base_finalmask = ensure_base_has_no_salamander(current["hysteria2_finalmask"])
    except SalamanderError as exc:
        raise XrayProfilesError(str(exc)) from exc

    old_obfs = str(current["hysteria2_obfs_mode"])
    old_password = str(current["hysteria2_obfs_password"])
    password_field = str(form.get("hysteria2_obfs_password") or "").strip()
    rotate_requested = _bool(form.get("hysteria2_obfs_rotate"), False)
    new_password = old_password
    obfs_enabled = requested_obfs != SALAMANDER_MODE_NONE
    if obfs_enabled:
        if not values["hysteria2_enabled"]:
            raise XrayProfilesError("Сначала включите Hysteria 2")
        installed = _installed_xray_version()
        required = minimum_version_for_mode(requested_obfs)
        if not salamander_version_supported(installed, required):
            title = "Gecko" if requested_obfs == GECKO_MODE else "Salamander"
            raise XrayProfilesError(
                f"Установленная версия Xray не поддерживает Hysteria2 {title}. "
                f"Требуется {required} или новее."
            )
        if rotate_requested and password_field:
            try:
                new_password = validate_password(password_field)
            except SalamanderError as exc:
                raise XrayProfilesError(str(exc)) from exc
        elif rotate_requested:
            new_password = generate_password()
        elif password_field:
            try:
                new_password = validate_password(password_field)
            except SalamanderError as exc:
                raise XrayProfilesError(str(exc)) from exc
        elif not password_ready(new_password):
            new_password = generate_password()
        try:
            new_password = validate_password(new_password)
        except SalamanderError as exc:
            raise XrayProfilesError(str(exc)) from exc
    else:
        # Keep the previous secret so either obfuscation mode can be re-enabled
        # without rotating credentials. It is not rendered while mode is none.
        if password_field:
            try:
                new_password = validate_password(password_field)
            except SalamanderError as exc:
                raise XrayProfilesError(str(exc)) from exc

    values.update(
        {
            "hysteria2_obfs_mode": requested_obfs,
            "hysteria2_obfs_password": new_password or None,
            "hysteria2_finalmask": base_finalmask,
            "hysteria2_salamander_managed": True,
            "hysteria2_uri_scheme": str(current["hysteria2_uri_scheme"]),
        }
    )

    config.update(values)
    host = str(form.get("host") or settings.host).strip()
    if not host:
        raise XrayProfilesError("Не указан публичный адрес сервера")

    return PreparedXraySettings(
        host=host,
        port=int(values["reality_tcp_port"]),
        config=config,
        salamander_changed=(
            old_obfs != requested_obfs
            or (obfs_enabled and old_password != new_password)
        ),
        salamander_rotated=(
            obfs_enabled
            and password_ready(old_password)
            and old_password != new_password
        ),
    )


def overview() -> dict[str, Any]:
    settings, config, tls = _config()
    values = _values(config, int(settings.port or 443))
    service_active = _service_active()
    key_ready = bool(
        config.get("public_key")
        and config.get("short_id")
        and "PLACEHOLDER" not in str(config.get("public_key"))
        and "PLACEHOLDER" not in str(config.get("short_id"))
    )
    tls_ready = bool(tls.get("https_ready"))
    vless_encryption = str(config.get("vless_encryption") or "").strip()
    encryption_ready = _vless_encryption_ready(vless_encryption)
    installed_version = _installed_xray_version()
    version_ready = _version_supported(installed_version)
    obfs = safe_status(
        values["hysteria2_obfs_mode"], values["hysteria2_obfs_password"]
    )
    obfs.update(
        {
            "version_ready": salamander_version_supported(
                installed_version, str(obfs["minimum_version"])
            ),
            "installed_version": installed_version,
            "base_finalmask_present": bool(values["hysteria2_finalmask"]),
            "salamander_minimum_version": SALAMANDER_MINIMUM_VERSION,
            "gecko_minimum_version": GECKO_MINIMUM_VERSION,
        }
    )

    def profile(
        profile_id: str,
        title: str,
        transport: str,
        security: str,
        port_key: str,
        enabled_key: str,
        *,
        path_key: str = "",
        tls_required: bool = False,
        encryption_required: bool = False,
        note: str,
        flow: str = "",
        mode_key: str = "",
        xmux_enabled_key: str = "",
    ) -> XrayProfile:
        enabled = bool(values[enabled_key])
        obfs_ready = not (
            profile_id == "hysteria2"
            and obfs["enabled"]
            and not obfs["password_configured"]
        )
        ready = (
            enabled
            and key_ready
            and version_ready
            and (tls_ready or not tls_required)
            and (encryption_ready or not encryption_required)
            and obfs_ready
        )
        if not version_ready:
            status = f"Нужен Xray {XRAY_MINIMUM_VERSION} или новее"
        elif tls_required and not tls_ready:
            status = "Нужен HTTPS"
        elif encryption_required and not encryption_ready:
            status = "Нужен VLESS Encryption"
        elif not obfs_ready:
            status = "Нужен пароль Hysteria2 obfs"
        elif not enabled:
            status = "Выключен"
        elif service_active and ready:
            status = "Работает"
        elif ready:
            status = "Готов к применению"
        else:
            status = "Требует настройки"
        return XrayProfile(
            id=profile_id,
            title=title,
            transport=transport,
            security=security,
            enabled=enabled,
            port=int(values[port_key]),
            path=str(values[path_key]) if path_key else "",
            tls_required=tls_required,
            ready=ready,
            status=status,
            note=note,
            flow=flow,
            encryption_required=encryption_required,
            encryption_ready=encryption_ready if encryption_required else False,
            mode=str(values[mode_key]) if mode_key else "",
            xmux_enabled=True if xmux_enabled_key else False,
            xmux=dict(XHTTP_XMUX_RF) if xmux_enabled_key else None,
        )

    profiles = [
        profile(
            "reality_tcp", "VLESS Reality TCP", "RAW / TCP", "REALITY",
            "reality_tcp_port", "reality_tcp_enabled",
            note="Основной прямой Reality inbound с XTLS Vision.",
            flow=REALITY_TCP_FLOW,
        ),
        profile(
            "xhttp_reality", "VLESS XHTTP Reality", "XHTTP / TCP", "REALITY",
            "xhttp_reality_port", "xhttp_reality_enabled",
            path_key="xhttp_reality_path",
            encryption_required=True,
            note="XHTTP + REALITY с обязательными VLESS Encryption и XTLS Vision.",
            flow=REALITY_TCP_FLOW,
            mode_key="xhttp_reality_mode",
            xmux_enabled_key="xhttp_reality_xmux_enabled",
        ),
        profile(
            "xhttp_tls", "VLESS XHTTP TLS", "XHTTP / TCP", "TLS",
            "xhttp_tls_port", "xhttp_tls_enabled",
            path_key="xhttp_tls_path", tls_required=True,
            encryption_required=True,
            note="XHTTP + TLS с обязательными VLESS Encryption и XTLS Vision.",
            flow=REALITY_TCP_FLOW,
            mode_key="xhttp_tls_mode",
            xmux_enabled_key="xhttp_tls_xmux_enabled",
        ),
        profile(
            "hysteria2", "Hysteria 2", "QUIC / UDP", "TLS",
            "hysteria2_port", "hysteria2_enabled",
            tls_required=True,
            note="Hysteria 2 с выбором Off / Salamander / Gecko на отдельном UDP-порту.",
        ),
    ]
    return {
        "host": settings.host,
        "profiles": profiles,
        "fingerprint": str(values["fingerprint"]),
        "fingerprint_values": FINGERPRINT_VALUES,
        "fingerprint_default": FINGERPRINT_DEFAULT,
        "tls_ready": tls_ready,
        "tls_domain": str(tls.get("domain") or ""),
        "certificate_path": str(tls.get("certificate_path") or ""),
        "service_active": service_active,
        "installed_version": installed_version,
        "required_version": XRAY_MINIMUM_VERSION,
        "minimum_version": XRAY_MINIMUM_VERSION,
        "version_ready": version_ready,
        "xhttp_modes": XHTTP_MODES,
        "xhttp_mode_options": XHTTP_MODE_OPTIONS,
        "xhttp_xmux_rf": dict(XHTTP_XMUX_RF),
        "key_ready": key_ready,
        "vless_encryption_ready": encryption_ready,
        "vless_encryption_algorithm": (
            vless_encryption.split(".", 1)[0] if encryption_ready else ""
        ),
        "hysteria2_obfs": obfs,
        "enabled_count": sum(1 for item in profiles if item.enabled),
        "ready_count": sum(1 for item in profiles if item.ready),
    }


def save(form: Any, *, transactional: bool = False) -> dict[str, Any]:
    prepared = _prepare(form)
    transaction: SettingsTransaction | None = None
    if transactional:
        transaction = begin_settings_transaction(
            "xray", prepared.host, prepared.port, prepared.config
        )
    else:
        updated = update_connection_settings(
            "xray", prepared.host, prepared.port, prepared.config
        )
        if not updated:
            raise XrayProfilesError("Настройки Xray не сохранены")

    result = overview()
    result["transaction_id"] = transaction.id if transaction is not None else None
    result["salamander_changed"] = prepared.salamander_changed
    result["salamander_rotated"] = prepared.salamander_rotated
    return result


def rollback_transaction(transaction_id: int, status: str = "rolled_back") -> bool:
    return rollback_settings_transaction(transaction_id, status=status)


def commit_transaction(transaction_id: int) -> bool:
    return commit_settings_transaction(transaction_id)


def pending_transaction() -> SettingsTransaction | None:
    return pending_settings_transaction("xray")


def salamander_secret() -> str:
    settings = get_connection_settings("xray")
    values = _values(dict(settings.config), int(settings.port or 443))
    secret = str(values["hysteria2_obfs_password"] or "")
    if not password_ready(secret):
        raise XrayProfilesError("Пароль Hysteria2 obfs ещё не создан")
    return secret


def new_salamander_password() -> str:
    return generate_password()
