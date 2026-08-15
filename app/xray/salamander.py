from __future__ import annotations

import copy
import secrets
from typing import Any


SALAMANDER_MODE_NONE = "none"
SALAMANDER_MODE = "salamander"
SALAMANDER_MODES = (SALAMANDER_MODE_NONE, SALAMANDER_MODE)
SALAMANDER_MINIMUM_VERSION = "26.3.27"
SALAMANDER_PASSWORD_BYTES = 24


class SalamanderError(ValueError):
    pass


def generate_password() -> str:
    """Return 24 cryptographically-random bytes as Base64URL without padding."""
    value = secrets.token_urlsafe(SALAMANDER_PASSWORD_BYTES)
    # token_urlsafe(24) is 32 URL-safe characters and never needs '=' padding.
    if len(value) < 32 or "=" in value:
        raise SalamanderError("Не удалось создать корректный пароль Salamander")
    return value


def normalise_mode(value: Any) -> str:
    mode = str(value or SALAMANDER_MODE_NONE).strip().lower()
    if mode not in SALAMANDER_MODES:
        raise SalamanderError("Неизвестный режим обфускации Hysteria2")
    return mode


def password_ready(value: Any) -> bool:
    text = str(value or "").strip()
    return len(text) >= 16 and not any(char.isspace() for char in text)


def validate_password(value: Any) -> str:
    text = str(value or "").strip()
    if not password_ready(text):
        raise SalamanderError(
            "Пароль Salamander должен содержать не менее 16 символов без пробелов"
        )
    if len(text) > 256:
        raise SalamanderError("Пароль Salamander слишком длинный")
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
    """Return a safe deep copy of the unmanaged/base FinalMask object."""
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise SalamanderError("Существующий FinalMask Hysteria2 повреждён")
    result = copy.deepcopy(value)
    for key in ("tcp", "udp"):
        if key in result and not isinstance(result[key], list):
            raise SalamanderError(f"FinalMask {key} должен быть массивом")
    if "quicParams" in result and not isinstance(result["quicParams"], dict):
        raise SalamanderError("FinalMask quicParams должен быть объектом")
    return result


def ensure_base_has_no_salamander(value: Any) -> dict[str, Any]:
    base = finalmask_base(value)
    if _contains_salamander(base):
        raise SalamanderError(
            "В базовом FinalMask уже существует внешний слой Salamander. "
            "SG-Gateway не будет перезаписывать его автоматически."
        )
    return base


def merge_finalmask(base_value: Any, mode: Any, password: Any) -> dict[str, Any]:
    """Render the Hysteria2 FinalMask for the selected obfuscation mode.

    SG-Gateway stores the pre-Salamander/base FinalMask separately.  Salamander
    is exclusive for the UDP FinalMask path: while it is enabled, stored base
    UDP masks are preserved in state but are not rendered into the live Xray
    config.  Disabling Salamander restores the exact stored base, including its
    UDP masks.  Non-UDP FinalMask fields (for example tcp and quicParams) stay
    active in both modes.
    """
    base = finalmask_base(base_value)
    selected = normalise_mode(mode)
    if selected == SALAMANDER_MODE_NONE:
        return base

    secret = validate_password(password)
    if _contains_salamander(base):
        raise SalamanderError(
            "Нельзя добавить управляемый Salamander поверх существующего слоя Salamander"
        )

    # Hysteria2 Salamander is the only live UDP FinalMask layer in this mode.
    # Keep any stored base UDP masks untouched in the database so they can be
    # restored exactly when Salamander is disabled.
    base["udp"] = [
        {
            "type": SALAMANDER_MODE,
            "settings": {"password": secret},
        }
    ]
    return base


def safe_status(mode: Any, password: Any) -> dict[str, Any]:
    selected = normalise_mode(mode)
    configured = selected == SALAMANDER_MODE and password_ready(password)
    return {
        "mode": selected,
        "enabled": selected == SALAMANDER_MODE,
        "password_configured": configured,
        "password_mask": "•" * 32 if configured else "",
        "minimum_version": SALAMANDER_MINIMUM_VERSION,
    }
