from __future__ import annotations

import configparser
import json
import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable


class WarpError(RuntimeError):
    pass


@dataclass(frozen=True)
class WarpProfile:
    private_key: str
    addresses: tuple[str, ...]
    dns: tuple[str, ...]
    mtu: int
    peer_public_key: str
    endpoint: str
    allowed_ips: tuple[str, ...]
    reserved: tuple[int, ...]


# Exact helper line used by the verified SG-Panel WARP implementation.
WGCF_VERSION = "v0.3.6"
WARP_TAG = "warp"
WARP_IPV4_ENDPOINT = "162.159.192.1:2408"


def state_dir() -> Path:
    return Path(os.getenv("SG_GATEWAY_WARP_STATE_DIR", "/var/lib/sg-gateway/warp"))


def account_json_path() -> Path:
    return state_dir() / "wgcf.json"


def xray_json_path() -> Path:
    return state_dir() / "wgcf.xray.json"


def account_path() -> Path:
    """Legacy upstream wgcf account path retained for migration."""
    return state_dir() / "wgcf-account.toml"


def profile_path() -> Path:
    """Legacy upstream wgcf profile path retained for migration."""
    return state_dir() / "wgcf-profile.conf"


def state_path() -> Path:
    return Path(os.getenv("SG_GATEWAY_WARP_STATE_PATH", "/etc/sg-gateway/warp.json"))


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _atomic_write_json(path: Path, payload: dict, mode: int = 0o600) -> None:
    import uuid

    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + f".tmp-{uuid.uuid4().hex}")
    with temporary.open("w", encoding="utf-8") as stream:
        json.dump(payload, stream, ensure_ascii=False, indent=2, sort_keys=True)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.chmod(temporary, mode)
    os.replace(temporary, path)


def _read_state() -> dict:
    try:
        payload = json.loads(state_path().read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def save_state(**updates: object) -> dict:
    payload = _read_state()
    payload.update(updates)
    payload["updated_at"] = _utc_now()
    # This file contains only public status. Private WARP credentials remain
    # in root-only JSON/profile files inside state_dir().
    _atomic_write_json(state_path(), payload, 0o644)
    return payload


def _split_csv(value: str) -> tuple[str, ...]:
    return tuple(item.strip() for item in value.split(",") if item.strip())


def _parse_reserved(value: str) -> tuple[int, ...]:
    raw = value.strip().strip("[]")
    if not raw:
        return ()
    values: list[int] = []
    for item in re.split(r"[\s,]+", raw):
        if not item:
            continue
        try:
            number = int(item)
        except ValueError as exc:
            raise WarpError("Поле Reserved в WARP-профиле имеет неверный формат") from exc
        if number < 0 or number > 255:
            raise WarpError("Значения Reserved должны быть в диапазоне 0..255")
        values.append(number)
    return tuple(values)


def _normalise_warp_outbound(document: object) -> dict:
    """Validate and normalise the exact wgcf-cli Xray outbound.

    This is the same contract used by SG-Panel: pin the deterministic IPv4
    Cloudflare endpoint, preserve generated credentials/reserved values and
    force Xray's userspace WireGuard implementation (noKernelTun).
    """
    if not isinstance(document, dict):
        raise WarpError("WARP outbound должен быть JSON-объектом")
    result = json.loads(json.dumps(document))
    if str(result.get("protocol", "")).lower() != "wireguard":
        raise WarpError("WARP outbound должен использовать protocol: wireguard")
    settings = result.get("settings")
    if not isinstance(settings, dict):
        raise WarpError("WARP outbound не содержит settings")
    if not str(settings.get("secretKey", "")).strip():
        raise WarpError("WARP outbound не содержит secretKey")
    address = settings.get("address")
    if not isinstance(address, list) or not any(str(item).strip() for item in address):
        raise WarpError("WARP outbound не содержит address")
    peers = settings.get("peers")
    if not isinstance(peers, list) or not peers or not isinstance(peers[0], dict):
        raise WarpError("WARP outbound не содержит peers")
    peer = peers[0]
    if not str(peer.get("publicKey", "")).strip():
        raise WarpError("WARP peer не содержит publicKey")
    peer["endpoint"] = WARP_IPV4_ENDPOINT
    peer.setdefault("allowedIPs", ["0.0.0.0/0", "::/0"])
    settings.setdefault("mtu", 1280)
    try:
        mtu = int(settings.get("mtu", 1280))
    except (TypeError, ValueError) as exc:
        raise WarpError("MTU WARP имеет неверный формат") from exc
    if mtu < 1280 or mtu > 1500:
        raise WarpError("MTU WARP должен быть в диапазоне 1280..1500")
    settings["mtu"] = mtu
    settings["noKernelTun"] = True
    result["protocol"] = "wireguard"
    result["tag"] = WARP_TAG
    result["settings"] = settings
    return result


def parse_xray_outbound(path: Path | None = None) -> dict:
    source = path or xray_json_path()
    if not source.is_file():
        raise WarpError("WARP Xray outbound ещё не создан")
    try:
        document = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise WarpError("Не удалось прочитать WARP Xray JSON") from exc
    return _normalise_warp_outbound(document)


def parse_profile(path: Path | None = None) -> WarpProfile:
    """Read the old wgcf INI profile for safe migration from Preview 48/49."""
    source = path or profile_path()
    if not source.is_file():
        raise WarpError("WARP-профиль ещё не создан")

    parser = configparser.ConfigParser(interpolation=None, strict=False)
    parser.optionxform = str
    try:
        parser.read(source, encoding="utf-8")
    except (OSError, configparser.Error) as exc:
        raise WarpError(f"Не удалось прочитать WARP-профиль: {exc}") from exc

    if "Interface" not in parser or "Peer" not in parser:
        raise WarpError("WARP-профиль не содержит Interface и Peer")
    interface = parser["Interface"]
    peer = parser["Peer"]

    private_key = interface.get("PrivateKey", "").strip()
    addresses = _split_csv(interface.get("Address", ""))
    dns = _split_csv(interface.get("DNS", ""))
    peer_public_key = peer.get("PublicKey", "").strip()
    endpoint = peer.get("Endpoint", "").strip()
    allowed_ips = _split_csv(peer.get("AllowedIPs", "0.0.0.0/0, ::/0"))
    reserved = _parse_reserved(interface.get("Reserved", "") or peer.get("Reserved", ""))
    try:
        mtu = int(interface.get("MTU", "1280").strip() or "1280")
    except ValueError as exc:
        raise WarpError("MTU в WARP-профиле имеет неверный формат") from exc

    if not private_key:
        raise WarpError("WARP-профиль не содержит PrivateKey")
    if not addresses:
        raise WarpError("WARP-профиль не содержит Address")
    if not peer_public_key:
        raise WarpError("WARP-профиль не содержит PublicKey peer")
    if not endpoint or ":" not in endpoint:
        raise WarpError("WARP-профиль не содержит корректный Endpoint")
    if not allowed_ips:
        allowed_ips = ("0.0.0.0/0", "::/0")
    if mtu < 1280 or mtu > 1500:
        raise WarpError("MTU WARP должен быть в диапазоне 1280..1500")

    return WarpProfile(
        private_key=private_key,
        addresses=addresses,
        dns=dns,
        mtu=mtu,
        peer_public_key=peer_public_key,
        endpoint=endpoint,
        allowed_ips=allowed_ips,
        reserved=reserved,
    )


def _legacy_outbound() -> dict:
    profile = parse_profile()
    settings: dict = {
        "secretKey": profile.private_key,
        "address": list(profile.addresses),
        "peers": [
            {
                "publicKey": profile.peer_public_key,
                "endpoint": profile.endpoint,
                "allowedIPs": list(profile.allowed_ips),
                "keepAlive": 25,
            }
        ],
        "mtu": profile.mtu,
        "workers": 2,
        "domainStrategy": "ForceIP",
        "noKernelTun": True,
    }
    if profile.reserved:
        settings["reserved"] = list(profile.reserved)
    return _normalise_warp_outbound(
        {"tag": WARP_TAG, "protocol": "wireguard", "settings": settings}
    )


def profile_ready() -> bool:
    # The web process intentionally cannot read root-only WARP credentials.
    # It may use only the public status marker; privileged hostd revalidates
    # the actual JSON/profile before every runtime mutation.
    if os.geteuid() != 0:
        return bool(_read_state().get("profile_ready"))
    try:
        if xray_json_path().is_file():
            parse_xray_outbound()
        else:
            _legacy_outbound()
    except WarpError:
        return False
    return True


def enabled() -> bool:
    state = _read_state()
    return bool(state.get("enabled")) and profile_ready()


def outbound(*, require_enabled: bool = True) -> dict | None:
    if require_enabled and not enabled():
        return None
    if xray_json_path().is_file():
        return parse_xray_outbound()
    return _legacy_outbound()


def scrubbed_profile() -> dict:
    try:
        document = outbound(require_enabled=False)
    except WarpError:
        return {}
    if not document:
        return {}
    settings = document.get("settings") if isinstance(document, dict) else {}
    settings = settings if isinstance(settings, dict) else {}
    peers = settings.get("peers") if isinstance(settings.get("peers"), list) else []
    peer = peers[0] if peers and isinstance(peers[0], dict) else {}
    address = settings.get("address") if isinstance(settings.get("address"), list) else []
    allowed = peer.get("allowedIPs") if isinstance(peer.get("allowedIPs"), list) else []
    reserved = settings.get("reserved") if isinstance(settings.get("reserved"), list) else []
    return {
        "addresses": [str(item) for item in address],
        "endpoint": str(peer.get("endpoint") or ""),
        "allowed_ips": [str(item) for item in allowed],
        "mtu": int(settings.get("mtu") or 1280),
        "reserved_present": bool(reserved),
    }


def export_document() -> str:
    document = outbound(require_enabled=False)
    if document is None:
        raise WarpError("WARP ещё не создан")
    return json.dumps(document, ensure_ascii=False, indent=2) + "\n"


def routing_uses_warp(payload: object) -> bool:
    if isinstance(payload, dict):
        if str(payload.get("outboundTag") or "") == WARP_TAG:
            return True
        return any(routing_uses_warp(value) for value in payload.values())
    if isinstance(payload, list):
        return any(routing_uses_warp(value) for value in payload)
    return False


def ensure_routing_supported(payload: object) -> None:
    if routing_uses_warp(payload) and not enabled():
        raise WarpError("В маршрутизации выбран WARP, но WARP ещё не установлен или выключен")


def overview() -> dict:
    state = _read_state()
    ready = profile_ready()
    active = bool(state.get("enabled")) and ready
    last_test = state.get("last_test") if isinstance(state.get("last_test"), dict) else {}
    profile = state.get("profile") if isinstance(state.get("profile"), dict) else {}
    if not profile and os.geteuid() == 0:
        profile = scrubbed_profile()
    return {
        "installed": ready,
        "enabled": active,
        "status": "enabled" if active else ("ready" if ready else "not-installed"),
        "status_label": "Активен" if active else ("Выключен" if ready else "Не установлен"),
        "wgcf_version": str(state.get("wgcf_version") or WGCF_VERSION),
        "profile": profile,
        "last_test": last_test,
        "updated_at": str(state.get("updated_at") or ""),
        "tag": WARP_TAG,
        "protocol_label": "wireguard · noKernelTun",
        "no_kernel_tun": True,
    }


def set_last_test(*, ok: bool, message: str, ip: str = "", warp: str = "") -> dict:
    return save_state(
        last_test={
            "ok": bool(ok),
            "message": str(message),
            "ip": str(ip),
            "warp": str(warp),
            "checked_at": _utc_now(),
        }
    )


def compatible_actions() -> tuple[str, ...]:
    return ("direct", "warp", "block") if enabled() else ("direct", "block")


def normalize_action(value: object, fallback: str = "direct") -> str:
    action = str(value or "").strip().lower()
    allowed = {"direct", "block", "warp"}
    return action if action in allowed else fallback


def validate_rules(actions: Iterable[str]) -> None:
    if any(str(action).lower() == "warp" for action in actions) and not enabled():
        raise WarpError("Сначала создайте WARP")
