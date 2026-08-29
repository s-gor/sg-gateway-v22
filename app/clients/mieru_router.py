from __future__ import annotations

from urllib.parse import parse_qs, urlencode


class MieruRouterError(ValueError):
    pass


def build_mieru_router_uri(value: str) -> str:
    """Convert SG-Gateway's normal mierus:// export to the compact router/ZB URI."""
    text = str(value or "").strip()
    if not text.startswith("mierus://"):
        raise MieruRouterError("Ожидалась обычная Mieru-ссылка mierus://")

    body, marker, fragment = text.partition("#")
    base, separator, query = body.partition("?")
    if not separator:
        raise MieruRouterError("В Mieru-ссылке отсутствуют параметры подключения")

    authority = base[len("mierus://") :]
    if not authority or "@" not in authority:
        raise MieruRouterError("В Mieru-ссылке отсутствуют учётные данные или сервер")

    params = parse_qs(query, keep_blank_values=True)
    port_raw = str((params.get("port") or [""])[0]).strip()
    try:
        port = int(port_raw)
    except (TypeError, ValueError) as exc:
        raise MieruRouterError("Некорректный порт Mieru") from exc
    if not 1 <= port <= 65535:
        raise MieruRouterError("Некорректный порт Mieru")

    transport = str((params.get("protocol") or ["TCP"])[0] or "TCP").strip().upper()
    if transport not in {"TCP", "UDP"}:
        raise MieruRouterError("Некорректный transport Mieru")

    compact_query = urlencode({"transport": transport})
    suffix = f"#{fragment}" if marker else ""
    return f"mieru://{authority}:{port}?{compact_query}{suffix}"
