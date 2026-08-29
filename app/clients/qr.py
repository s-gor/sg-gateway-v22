from __future__ import annotations

import json
from io import BytesIO
from urllib.parse import parse_qs, urlsplit
from xml.etree import ElementTree as ET


SVG_NAMESPACE = "http://www.w3.org/2000/svg"
SUBSCRIPTION_TITLE = "SG · ПОДПИСКА"
SINGLE_PROFILE_TITLE = "SG · ОДИНОЧНЫЙ ПРОФИЛЬ"
SUBSCRIPTION_SUBTITLE = "Все назначенные профили"
MAX_SUBTITLE_LENGTH = 42


class ClientQrError(ValueError):
    pass


def _truncate_label(value: str, limit: int = MAX_SUBTITLE_LENGTH) -> str:
    text = " ".join(str(value or "").split())
    if len(text) <= limit:
        return text
    return text[: max(1, limit - 1)].rstrip() + "…"


def _vless_profile_name(payload: str) -> str:
    parsed = urlsplit(payload)
    query = parse_qs(parsed.query)
    transport = str((query.get("type") or [""])[0]).strip().lower()
    security = str((query.get("security") or [""])[0]).strip().lower()

    if transport in {"tcp", "raw"} and security == "reality":
        return "VLESS Reality TCP"
    if transport == "xhttp" and security == "reality":
        return "VLESS XHTTP Reality"
    if transport == "xhttp" and security == "tls":
        return "VLESS XHTTP TLS"
    return "VLESS"


def _profile_name(payload: str) -> str:
    stripped = payload.lstrip()
    lowered = stripped.lower()

    if lowered.startswith("# sg-gateway amneziawg 3.1"):
        return "AmneziaWG 3.1"
    if lowered.startswith("# sg-gateway amneziawg 3.0"):
        return "AmneziaWG 3.0"
    if lowered.startswith("# sg-gateway amneziawg"):
        return "AmneziaWG 2.0"

    parsed = urlsplit(stripped)
    scheme = parsed.scheme.lower()
    if scheme == "awg31":
        return "AmneziaWG 3.1"
    if scheme == "vless":
        return _vless_profile_name(stripped)

    scheme_names = {
        "hysteria2": "Hysteria 2",
        "hy2": "Hysteria 2",
        "mieru": "Mieru",
        "mierus": "Mieru",
        "anytls": "AnyTLS",
        "tuic": "TUIC v5",
    }
    if scheme in scheme_names:
        return scheme_names[scheme]

    if stripped.startswith("{"):
        try:
            document = json.loads(stripped)
        except (TypeError, ValueError, json.JSONDecodeError):
            document = None
        if isinstance(document, dict):
            return "Mieru JSON"

    return "Профиль подключения"


def _caption(payload: str) -> tuple[str, str]:
    scheme = urlsplit(payload.lstrip()).scheme.lower()
    if scheme in {"http", "https"}:
        return SUBSCRIPTION_TITLE, SUBSCRIPTION_SUBTITLE
    return SINGLE_PROFILE_TITLE, _truncate_label(_profile_name(payload))


def _format_number(value: float) -> str:
    rounded = round(float(value), 3)
    if rounded.is_integer():
        return str(int(rounded))
    return f"{rounded:.3f}".rstrip("0").rstrip(".")


def _fit_font_size(text: str, width: float, maximum: float, minimum: float) -> float:
    estimated_units = max(1.0, len(text) * 0.58)
    available = max(1.0, width - 2.4)
    return max(minimum, min(maximum, available / estimated_units))


def _append_caption(svg: str, payload: str) -> str:
    ET.register_namespace("", SVG_NAMESPACE)
    root = ET.fromstring(svg)
    view_box = root.attrib.get("viewBox", "").split()
    if len(view_box) != 4:
        raise ClientQrError("Не удалось добавить подпись к QR-коду")

    try:
        x, y, width, qr_height = (float(item) for item in view_box)
    except ValueError as exc:
        raise ClientQrError("Не удалось добавить подпись к QR-коду") from exc

    title, subtitle = _caption(payload)
    title_size = _fit_font_size(title, width, maximum=3.0, minimum=1.45)
    subtitle_size = _fit_font_size(subtitle, width, maximum=2.35, minimum=1.2)
    top_padding = 1.15
    line_gap = 0.75
    bottom_padding = 1.15
    caption_height = (
        top_padding + title_size + line_gap + subtitle_size + bottom_padding
    )
    total_height = qr_height + caption_height

    root.set(
        "viewBox",
        " ".join(
            _format_number(item)
            for item in (x, y, width, total_height)
        ),
    )

    height_value = root.attrib.get("height", "")
    if height_value.endswith("mm"):
        root.set("height", f"{_format_number(total_height)}mm")
    elif height_value:
        root.set("height", _format_number(total_height))

    def tag(name: str) -> str:
        return f"{{{SVG_NAMESPACE}}}{name}"

    ET.SubElement(
        root,
        tag("rect"),
        {
            "x": _format_number(x),
            "y": _format_number(y + qr_height),
            "width": _format_number(width),
            "height": _format_number(caption_height),
            "fill": "#ffffff",
        },
    )

    center_x = x + width / 2
    title_y = y + qr_height + top_padding + title_size
    subtitle_y = title_y + line_gap + subtitle_size
    common = {
        "x": _format_number(center_x),
        "text-anchor": "middle",
        "font-family": "Arial, Helvetica, sans-serif",
        "fill": "#111111",
    }

    title_node = ET.SubElement(
        root,
        tag("text"),
        {
            **common,
            "y": _format_number(title_y),
            "font-size": _format_number(title_size),
            "font-weight": "700",
        },
    )
    title_node.text = title

    subtitle_node = ET.SubElement(
        root,
        tag("text"),
        {
            **common,
            "y": _format_number(subtitle_y),
            "font-size": _format_number(subtitle_size),
            "font-weight": "400",
        },
    )
    subtitle_node.text = subtitle

    return ET.tostring(root, encoding="unicode", xml_declaration=True)


def build_qr_svg(payload: str, *, include_caption: bool = False) -> str:
    """Build an SVG QR, optionally with a human-readable caption.

    VLESS Encryption adds a large client key to the URL. Error correction L
    leaves the most QR capacity while retaining normal scanner compatibility.
    The caption is outside the QR matrix and never changes the encoded payload.
    """
    value = str(payload or "").strip()
    if not value:
        raise ClientQrError("Нельзя создать QR для пустой конфигурации")

    import qrcode
    import qrcode.image.svg
    from qrcode.exceptions import DataOverflowError

    factory = qrcode.image.svg.SvgPathImage
    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=8,
        border=2,
    )
    qr.add_data(value, optimize=0)
    try:
        qr.make(fit=True)
    except (DataOverflowError, ValueError) as exc:
        # qrcode 7.x can report an overflow either as DataOverflowError or as
        # ValueError("Invalid version (was 41, expected 1 to 40)"). Only
        # normalize that known capacity error; unrelated ValueError instances
        # must still surface as programming/configuration errors.
        if isinstance(exc, ValueError) and not isinstance(exc, DataOverflowError):
            if "Invalid version" not in str(exc):
                raise
        raise ClientQrError(
            "Ссылка слишком велика для одного QR-кода; используйте скачивание ссылки"
        ) from exc

    image = qr.make_image(image_factory=factory)
    buffer = BytesIO()
    image.save(buffer)
    svg = buffer.getvalue().decode("utf-8")
    return _append_caption(svg, value) if include_caption else svg
