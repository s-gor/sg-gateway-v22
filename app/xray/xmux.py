from __future__ import annotations

import json
import re
from typing import Any, Mapping

from app.connections.settings import get_connection_settings, update_connection_settings


XMUX_MODE_STANDARD = "auto"
XMUX_MODE_REDUCED = "reduced"
XMUX_MODE_EXPERT = "expert"
XMUX_MODES = (XMUX_MODE_STANDARD, XMUX_MODE_REDUCED, XMUX_MODE_EXPERT)

# Keep the internal mode names identical to SG-Panel for compatibility:
#   auto    -> fixed current Xray preset
#   reduced -> fixed Russian-network fast-rotation preset
#   expert  -> manual XMUX fields plus Client Extra JSON
XMUX_STANDARD_PRESET: dict[str, object] = {
    "maxConcurrency": 0,
    "maxConnections": 3,
    "cMaxReuseTimes": 0,
    "hMaxRequestTimes": "600-900",
    "hMaxReusableSecs": "1800-3000",
    "hKeepAlivePeriod": 0,
}
XMUX_REDUCED_PRESET: dict[str, object] = {
    "maxConcurrency": 5,
    "maxConnections": 0,
    "cMaxReuseTimes": 0,
    "hMaxRequestTimes": "300-600",
    "hMaxReusableSecs": "900-1800",
    "hKeepAlivePeriod": 0,
}
XMUX_FIELD_NAMES = (
    "maxConcurrency",
    "maxConnections",
    "cMaxReuseTimes",
    "hMaxRequestTimes",
    "hMaxReusableSecs",
    "hKeepAlivePeriod",
)
_XMUX_RANGE_RE = re.compile(r"^(\d+)(?:-(\d+))?$")

XMUX_MODE_OPTIONS = (
    {
        "value": XMUX_MODE_STANDARD,
        "title": "Стандартный",
        "note": "Фиксированный актуальный пресет Xray-core 26.7.28.",
    },
    {
        "value": XMUX_MODE_REDUCED,
        "title": "Для РФ — быстрая ротация",
        "note": "Фиксированный профиль с более быстрой ротацией соединений.",
    },
    {
        "value": XMUX_MODE_EXPERT,
        "title": "Ручной",
        "note": "Шесть XMUX-полей вручную; дополнительные Client Extra поля сохраняются.",
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


def _manual_value(name: str, value: Any) -> int | str:
    text = str(value if value is not None else "").strip()
    match = _XMUX_RANGE_RE.fullmatch(text)
    if not match:
        raise XmuxError(f"{name}: укажите 0 или неотрицательное число/диапазон A-B")
    start = int(match.group(1))
    end_raw = match.group(2)
    if end_raw is None:
        return start
    if name == "hKeepAlivePeriod":
        raise XmuxError("hKeepAlivePeriod: допустимо только целое число")
    end = int(end_raw)
    if start > end:
        raise XmuxError(f"{name}: начало диапазона не может быть больше конца")
    return f"{start}-{end}"


def manual_xmux_from_form(form: Any) -> dict[str, int | str]:
    values: dict[str, int | str] = {}
    for name in XMUX_FIELD_NAMES:
        values[name] = _manual_value(name, form.get(f"xhttp_xmux_{name}"))
    validate_xmux_conflicts({"xmux": values}, label="Ручной XMUX")
    return values


def effective_client_extra(config: Mapping[str, Any]) -> dict[str, Any]:
    mode = normalise_mode(config.get("xhttp_xmux_mode"))
    extra = parse_client_extra(config.get("xhttp_extra_client_json"))

    if mode == XMUX_MODE_EXPERT:
        if not isinstance(extra.get("xmux"), Mapping):
            raise XmuxError("Для ручного режима нужен объект xmux в Client Extra JSON")
        validate_xmux_conflicts(extra)
        return extra

    # Configurations saved by this UI carry concrete XMUX values. Honor them
    # verbatim on later exports so an application update cannot silently change
    # a user's already-saved preset.
    if config.get("xhttp_xmux_preset_revision") and isinstance(extra.get("xmux"), Mapping):
        validate_xmux_conflicts(extra)
        return extra

    result = dict(extra)
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

    stored_xmux = stored.get("xmux")
    if isinstance(stored_xmux, Mapping):
        manual = {
            name: stored_xmux.get(name, XMUX_STANDARD_PRESET[name])
            for name in XMUX_FIELD_NAMES
        }
    else:
        fallback = XMUX_REDUCED_PRESET if mode == XMUX_MODE_REDUCED else XMUX_STANDARD_PRESET
        manual = dict(fallback)

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
        "manual": manual,
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

    if mode == XMUX_MODE_EXPERT and any(
        form.get(f"xhttp_xmux_{name}") is not None for name in XMUX_FIELD_NAMES
    ):
        extra = dict(extra)
        extra["xmux"] = manual_xmux_from_form(form)

    candidate = dict(config)
    candidate["xhttp_xmux_mode"] = mode
    candidate["xhttp_extra_client_json"] = extra
    candidate["xhttp_reality_mode"] = "stream-one"
    candidate.pop("xhttp_xmux_preset_revision", None)

    # Persist the concrete XMUX object for every mode. The mode remains a
    # UI/compatibility marker. Fixed presets also get a revision marker so later
    # application updates keep the concrete values already saved by the user.
    candidate["xhttp_extra_client_json"] = effective_client_extra(candidate)
    if mode == XMUX_MODE_EXPERT:
        candidate.pop("xhttp_xmux_preset_revision", None)
    else:
        candidate["xhttp_xmux_preset_revision"] = "xray-26.7.28"

    if not update_connection_settings("xray", settings.host, settings.port, candidate):
        raise XmuxError("Не удалось сохранить настройки XMUX")
    return state_from_config(candidate)
