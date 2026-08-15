from __future__ import annotations

import json
from dataclasses import dataclass

from app.clients.exports import (
    build_anytls_link,
    build_awg_config,
    build_mieru_json,
    build_mieru_link,
    build_subscription_url,
    build_tuic_link,
    build_xray_profile_link,
    protocol_ready,
)
from app.clients.repository import (
    Client,
    Device,
    get_primary_device,
    list_client_deployments,
    list_device_credentials,
)
from app.xray.profiles import overview as xray_profiles_overview


@dataclass(frozen=True)
class AccessCard:
    kind: str
    title: str
    status: str
    description: str
    primary_action: str
    export_url: str
    qr_url: str
    payload: str
    show_qr: bool = True
    secondary_url: str = ""
    secondary_label: str = ""
    secondary_payload: str = ""
    secondary_qr_url: str = ""
    tertiary_url: str = ""
    tertiary_label: str = ""


def _deployment_map(client: Client, device: Device | None = None) -> dict:
    rows = (
        list_device_credentials(device.id)
        if device is not None
        else list_client_deployments(client.id)
    )
    return {item.engine: item for item in rows}


def _status(
    client: Client,
    device: Device | None,
    deployment,
    *,
    ready: bool = True,
) -> str:
    resolved = device if device is not None else get_primary_device(client.id)
    if not client.enabled or (resolved is not None and not resolved.enabled):
        return "disabled"
    if deployment is None:
        return "missing"
    if not ready:
        return "locked"
    return deployment.status


def _urls(client: Client, device: Device | None, kind: str) -> tuple[str, str]:
    resolved = device if device is not None else get_primary_device(client.id)
    if resolved is None:
        return "", ""
    base = f"/clients/{client.id}/devices/{resolved.id}/protocols/{kind}"
    return base, base + "/qr"


def build_access_cards(
    client: Client,
    device: Device | None = None,
) -> list[AccessCard]:
    deployments = _deployment_map(client, device)
    cards: list[AccessCard] = []

    awg = deployments.get("amneziawg")
    if awg is not None:
        status = _status(client, device, awg)
        export_url, qr_url = _urls(client, device, "amneziawg")
        cards.append(
            AccessCard(
                kind="amneziawg",
                title="AmneziaWG",
                status=status,
                description="Полная AWG-конфигурация с параметрами маскировки.",
                primary_action="Скачать конфигурацию",
                export_url=export_url,
                qr_url=qr_url,
                payload=build_awg_config(client, device).body if status == "applied" else "",
            )
        )

    xray = deployments.get("xray")
    if xray is not None:
        state = xray_profiles_overview()
        selected: list[str] = []
        try:
            value = json.loads(xray.config_json or "{}")
            if isinstance(value.get("profiles"), list):
                selected = [str(item) for item in value["profiles"]]
        except (TypeError, ValueError, json.JSONDecodeError):
            selected = []
        selected = selected or ["reality_tcp", "xhttp_reality"]
        definitions = {
            "reality_tcp": (
                "xray-reality-tcp",
                "VLESS Reality TCP",
                "Основной VLESS Reality inbound с XTLS Vision.",
            ),
            "xhttp_reality": (
                "xray-xhttp-reality",
                "VLESS XHTTP Reality",
                "Отдельный XHTTP inbound с защитой REALITY.",
            ),
            "xhttp_tls": (
                "xray-xhttp-tls",
                "VLESS XHTTP TLS",
                "XHTTP через обычный домен и TLS-сертификат.",
            ),
            "hysteria2": (
                "hysteria2",
                "Hysteria 2",
                "Отдельное QUIC/UDP-подключение через TLS.",
            ),
        }
        profiles = {item.id: item for item in state["profiles"]}
        for profile_id in selected:
            definition = definitions.get(profile_id)
            profile = profiles.get(profile_id)
            if definition is None or profile is None:
                continue
            kind, title, description = definition
            if profile_id in {"xhttp_reality", "xhttp_tls"} and getattr(profile, "mode", ""):
                description = f"{description} Клиентский mode: {profile.mode}."
            ready = bool(profile.enabled and profile.ready)
            status = _status(client, device, xray, ready=ready)
            payload = (
                build_xray_profile_link(client, profile_id, device).body
                if status == "applied" and protocol_ready(client, kind, device)
                else ""
            )
            export_url, qr_url = _urls(client, device, kind)
            cards.append(
                AccessCard(
                    kind=kind,
                    title=title,
                    status=status,
                    description=description,
                    primary_action="Скачать ссылку",
                    export_url=export_url,
                    qr_url=qr_url,
                    payload=payload,
                )
            )

    mihomo = deployments.get("mihomo")
    if mihomo is not None:
        ready = protocol_ready(client, "mieru", device)
        status = _status(client, device, mihomo, ready=ready)
        link_url, link_qr_url = _urls(client, device, "mieru")
        json_url, json_qr_url = _urls(client, device, "mieru-json")
        yaml_url, _ = _urls(client, device, "mihomo")
        cards.append(
            AccessCard(
                kind="mihomo",
                title="Mieru",
                status=status,
                description=(
                    "Обычная Mieru-ссылка для SG Client и отдельный JSON "
                    "для клиентов, которые импортируют Mieru только как конфигурацию."
                ),
                primary_action="Скачать Mieru-ссылку",
                export_url=link_url,
                qr_url=link_qr_url,
                payload=build_mieru_link(client, device).body if status == "applied" else "",
                show_qr=True,
                secondary_url=(
                    json_url if protocol_ready(client, "mieru-json", device) else ""
                ),
                secondary_label="Скачать Mieru JSON",
                secondary_payload=(
                    build_mieru_json(client, device).body
                    if status == "applied"
                    and protocol_ready(client, "mieru-json", device)
                    else ""
                ),
                secondary_qr_url=(
                    json_qr_url
                    if status == "applied"
                    and protocol_ready(client, "mieru-json", device)
                    else ""
                ),
                tertiary_url=(
                    yaml_url if protocol_ready(client, "mihomo", device) else ""
                ),
                tertiary_label="Mihomo YAML",
            )
        )

    anytls = deployments.get("anytls")
    if anytls is not None:
        ready = protocol_ready(client, "anytls", device)
        status = _status(client, device, anytls, ready=ready)
        export_url, qr_url = _urls(client, device, "anytls")
        cards.append(
            AccessCard(
                kind="anytls",
                title="AnyTLS",
                status=status,
                description="Один AnyTLS inbound на отдельном TCP-порту.",
                primary_action="Скачать AnyTLS-ссылку",
                export_url=export_url,
                qr_url=qr_url,
                payload=build_anytls_link(client, device).body if status == "applied" else "",
            )
        )

    tuic = deployments.get("tuic")
    if tuic is not None:
        ready = protocol_ready(client, "tuic", device)
        status = _status(client, device, tuic, ready=ready)
        export_url, qr_url = _urls(client, device, "tuic")
        cards.append(
            AccessCard(
                kind="tuic",
                title="TUIC v5",
                status=status,
                description="Один TUIC v5 inbound на отдельном UDP-порту.",
                primary_action="Скачать TUIC-ссылку",
                export_url=export_url,
                qr_url=qr_url,
                payload=build_tuic_link(client, device).body if status == "applied" else "",
            )
        )

    sgclient = deployments.get("sgclient")
    if sgclient is not None:
        status = _status(client, device, sgclient)
        subscription_url = build_subscription_url(client, device)
        _, qr_url = _urls(client, device, "subscription")
        cards.append(
            AccessCard(
                kind="subscription",
                title="Подписка устройства",
                status=status,
                description="Персональная URL-подписка для совместимых клиентов.",
                primary_action="Скопировать ссылку",
                export_url="",
                qr_url=qr_url,
                payload=subscription_url if status == "applied" else "",
                show_qr=True,
            )
        )

    return cards
