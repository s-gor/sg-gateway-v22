from __future__ import annotations

import copy
import secrets
from typing import Any


SALAMANDER_MODE_NONE = "none"
SALAMANDER_MODE = "salamander"
GECKO_MODE = "gecko"
SALAMANDER_MODES = (SALAMANDER_MODE_NONE, SALAMANDER_MODE, GECKO_MODE)
SALAMANDER_MINIMUM_VERSION = "26.3.27"
GECKO_MINIMUM_VERSION = "26.6.27"
SALAMANDER_PASSWORD_BYTES = 24
GECKO_PACKET_SIZE = "512-1200"
MANAGED_VARIANT_MARKER = "_sg_hysteria2_obfs_managed"


class SalamanderError(ValueError):
    pass


def generate_password() -> str:
    """Return 24 cryptographically-random bytes as Base64URL without padding."""
    value = secrets.token_urlsafe(SALAMANDER_PASSWORD_BYTES)
    if len(value) < 32 or "=" in value:
        raise SalamanderError("Не удалось создать корректный пароль Hysteria2 obfs")
    return value


def normalise_mode(value: Any) -> str:
    mode = str(value or SALAMANDER_MODE_NONE).strip().lower()
    if mode not in SALAMANDER_MODES:
        raise SalamanderError("Неизвестный режим обфускации Hysteria2")
    return mode


def minimum_version_for_mode(value: Any) -> str:
    mode = normalise_mode(value)
    if mode == GECKO_MODE:
        return GECKO_MINIMUM_VERSION
    return SALAMANDER_MINIMUM_VERSION


def password_ready(value: Any) -> bool:
    text = str(value or "").strip()
    return len(text) >= 16 and not any(char.isspace() for char in text)


def validate_password(value: Any) -> str:
    text = str(value or "").strip()
    if not password_ready(text):
        raise SalamanderError(
            "Пароль Hysteria2 obfs должен содержать не менее 16 символов без пробелов"
        )
    if len(text) > 256:
        raise SalamanderError("Пароль Hysteria2 obfs слишком длинный")
    return text


def version_key(value: Any) -> tuple[int, ...]:
    try:
        return tuple(int(part) for part in str(value or "").lstrip("v").split("."))
    except (TypeError, ValueError):
        return ()


def version_supported(installed: Any, minimum: str = SALAMANDER_MINIMUM_VERSION) -> bool:
    current = version_key(installed)
    required = version_key(minimum)
    if not current or not required:
        return False
    width = max(len(current), len(required))
    return current + (0,) * (width - len(current)) >= required + (0,) * (width - len(required))


def _contains_salamander(finalmask: dict[str, Any]) -> bool:
    udp = finalmask.get("udp")
    if not isinstance(udp, list):
        return False
    return any(
        isinstance(item, dict)
        and str(item.get("type") or "").strip().lower() == SALAMANDER_MODE
        for item in udp
    )


def finalmask_base(value: Any) -> dict[str, Any]:
    """Return a safe stored base FinalMask with an internal managed marker.

    The marker intentionally keeps the stored base non-empty even when there
    are no unmanaged FinalMask fields. HostD therefore does not rediscover the
    currently-live managed Salamander/Gecko layer as unmanaged state when the
    administrator switches between the two variants. ``merge_finalmask``
    removes this marker before rendering the live Xray JSON.
    """
    if value is None:
        result: dict[str, Any] = {}
    elif not isinstance(value, dict):
        raise SalamanderError("Существующий FinalMask Hysteria2 повреждён")
    else:
        result = copy.deepcopy(value)
    for key in ("tcp", "udp"):
        if key in result and not isinstance(result[key], list):
            raise SalamanderError(f"FinalMask {key} должен быть массивом")
    if "quicParams" in result and not isinstance(result["quicParams"], dict):
        raise SalamanderError("FinalMask quicParams должен быть объектом")
    result[MANAGED_VARIANT_MARKER] = True
    return result


def ensure_base_has_no_salamander(value: Any) -> dict[str, Any]:
    base = finalmask_base(value)
    if _contains_salamander(base):
        raise SalamanderError(
            "В базовом FinalMask уже существует управляемый Salamander/Gecko слой. "
            "SG-Gateway не будет перезаписывать его автоматически."
        )
    return base


def merge_finalmask(base_value: Any, mode: Any, password: Any) -> dict[str, Any]:
    """Render Off, Salamander or Gecko without mutating stored base FinalMask.

    Xray uses FinalMask type ``salamander`` for both variants. Plain Salamander
    renders only its password. Gecko uses the same primitive plus
    ``packetSize=512-1200``, which enables handshake fragmentation/padding.
    The private SG-Gateway marker is never emitted into the live Xray config.
    """
    base = finalmask_base(base_value)
    base.pop(MANAGED_VARIANT_MARKER, None)
    selected = normalise_mode(mode)
    if selected == SALAMANDER_MODE_NONE:
        return base

    secret = validate_password(password)
    if _contains_salamander(base):
        raise SalamanderError(
            "Нельзя добавить управляемый Salamander/Gecko поверх существующего слоя Salamander"
        )

    settings: dict[str, Any] = {"password": secret}
    if selected == GECKO_MODE:
        settings["packetSize"] = GECKO_PACKET_SIZE

    base["udp"] = [
        {
            "type": SALAMANDER_MODE,
            "settings": settings,
        }
    ]
    return base


def safe_status(mode: Any, password: Any) -> dict[str, Any]:
    selected = normalise_mode(mode)
    enabled = selected != SALAMANDER_MODE_NONE
    configured = enabled and password_ready(password)
    return {
        "mode": selected,
        "variant": selected,
        "enabled": enabled,
        "password_configured": configured,
        "password_mask": "•" * 32 if configured else "",
        "minimum_version": minimum_version_for_mode(selected),
        "packet_size": GECKO_PACKET_SIZE if selected == GECKO_MODE else "",
    }
