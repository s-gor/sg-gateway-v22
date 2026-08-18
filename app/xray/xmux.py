from __future__ import annotations

import json
from typing import Any, Mapping

from app.connections.settings import get_connection_settings, update_connection_settings


XMUX_MODE_STANDARD = "auto"
XMUX_MODE_REDUCED = "reduced"
XMUX_MODE_EXPERT = "expert"
XMUX_MODES = (XMUX_MODE_STANDARD, XMUX_MODE_REDUCED, XMUX_MODE_EXPERT)

# Keep the internal mode names identical to SG-Panel for compatibility:
#   auto    -> Standard preset
#   reduced -> Для РФ — уменьшенный
#   expert  -> manual Client Extra JSON
XMUX_STANDARD_PRESET: dict[str, object] = {
    "maxConnections": "2-4",
    "cMaxReuseTimes": "300-600",
    "hMaxRequestTimes": "1000-2000",
    "hMaxReusableSecs": "1200-2400",
    "hKeepAlivePeriod": 600,
}
XMUX_REDUCED_PRESET: dict[str, object] = {
    "maxConcurrency": 0,
    "maxConnections": "6",
    "cMaxReuseTimes": 0,
    "hMaxRequestTimes": "600-900",
    "hMaxReusableSecs": "1800-3000",
    "hKeepAlivePeriod": 0,
}

XMUX_MODE_OPTIONS = (
    {
        "value": XMUX_MODE_STANDARD,
        "title": "Стандартный",
        "note": "Рекомендуемый пресет SG-Panel для обычных сетей.",
    },
    {
        "value": XMUX_MODE_REDUCED,
        "title": "Для РФ — уменьшенный",
        "note": "Уменьшенное число соединений; maxConcurrency остаётся 0.",
    },
    {
        "value": XMUX_MODE_EXPERT,
        "title": "Ручной",
        "note": "Полный Client Extra JSON. Объект xmux обязателен.",
    },
)


class XmuxError(ValueError):
    pass


def normalise_mode(value: Any) -> str:
    mode = str(value or XMUX_MODE_STANDARD).strip().lower()
    if mode not in XMUX_MODES:
        raise XmuxError("Некорректный режим XMUX")
    return mode


def parse_client_extra(value: Any) -> dict[str, Any]:
    if value is None or value == "":
        return {}
    if isinstance(value, Mapping):
        return dict(value)
    if not isinstance(value, str):
        raise XmuxError("Client Extra должен быть JSON-объектом")
    text = value.strip()
    if not text:
        return {}
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        raise XmuxError(f"Client Extra JSON: {exc.msg}") from exc
    if not isinstance(parsed, dict):
        raise XmuxError("Client Extra должен быть JSON-объектом")
    return parsed


def _positive(value: Any) -> bool:
    if isinstance(value, bool):
        return bool(value)
    if isinstance(value, (int, float)):
        return value > 0
    text = str(value or "").strip()
    if not text:
        return False
    if "-" in text:
        parts = text.split("-", 1)
        try:
            return max(int(parts[0]), int(parts[1])) > 0
        except ValueError:
            return False
    try:
        return int(text) > 0
    except ValueError:
        return False


def validate_xmux_conflicts(extra: Mapping[str, Any], *, label: str = "Client Extra") -> None:
    xmux = extra.get("xmux")
    if xmux is None:
        return
    if not isinstance(xmux, Mapping):
        raise XmuxError(f"{label}: xmux должен быть объектом")
    if _positive(xmux.get("maxConnections")) and _positive(xmux.get("maxConcurrency")):
        raise XmuxError(
            f"{label}: XMUX не допускает одновременно положительные maxConnections и maxConcurrency"
        )


def effective_client_extra(config: Mapping[str, Any]) -> dict[str, Any]:
    mode = normalise_mode(config.get("xhttp_xmux_mode"))
    extra = parse_client_extra(config.get("xhttp_extra_client_json"))

    if mode == XMUX_MODE_EXPERT:
        if not isinstance(extra.get("xmux"), Mapping):
            raise XmuxError("Для ручного режима нужен объект xmux в Client Extra JSON")
        validate_xmux_conflicts(extra)
        return extra

    result = dict(extra)
    result.pop("xmux", None)
    result["xmux"] = dict(
        XMUX_STANDARD_PRESET if mode == XMUX_MODE_STANDARD else XMUX_REDUCED_PRESET
    )
    validate_xmux_conflicts(result)
    return result


def state_from_config(config: Mapping[str, Any]) -> dict[str, Any]:
    try:
        mode = normalise_mode(config.get("xhttp_xmux_mode"))
    except XmuxError:
        mode = XMUX_MODE_STANDARD
    try:
        stored = parse_client_extra(config.get("xhttp_extra_client_json"))
    except XmuxError:
        stored = {}
    effective_config = dict(config)
    effective_config["xhttp_xmux_mode"] = mode
    effective_config["xhttp_extra_client_json"] = stored
    try:
        effective = effective_client_extra(effective_config)
        error = ""
    except XmuxError as exc:
        effective = {}
        error = str(exc)
    return {
        "mode": mode,
        "mode_options": XMUX_MODE_OPTIONS,
        "stored": stored,
        "stored_json": json.dumps(stored, ensure_ascii=False, indent=2, sort_keys=True),
        "effective": effective,
        "effective_json": json.dumps(effective, ensure_ascii=False, indent=2, sort_keys=True),
        "standard": dict(XMUX_STANDARD_PRESET),
        "reduced": dict(XMUX_REDUCED_PRESET),
        "error": error,
        "reality_client_mode": "stream-one",
        "tls_client_mode": str(config.get("xhttp_tls_mode") or "auto"),
    }


def overview() -> dict[str, Any]:
    settings = get_connection_settings("xray")
    return state_from_config(dict(settings.config))


def update_from_form(form: Any) -> dict[str, Any]:
    settings = get_connection_settings("xray")
    config = dict(settings.config)
    mode = normalise_mode(form.get("xhttp_xmux_mode", config.get("xhttp_xmux_mode")))

    raw_extra = form.get("xhttp_extra_client_json")
    if raw_extra is None:
        extra = parse_client_extra(config.get("xhttp_extra_client_json"))
    else:
        extra = parse_client_extra(raw_extra)

    candidate = dict(config)
    candidate["xhttp_xmux_mode"] = mode
    candidate["xhttp_extra_client_json"] = extra
    # SG-Panel contract: Reality XHTTP server is auto and client is fixed stream-one.
    candidate["xhttp_reality_mode"] = "stream-one"

    # Validate the exact Client Extra that will be exported before saving.
    effective_client_extra(candidate)

    if not update_connection_settings("xray", settings.host, settings.port, candidate):
        raise XmuxError("Не удалось сохранить настройки XMUX")
    return state_from_config(candidate)
