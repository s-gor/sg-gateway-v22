from __future__ import annotations

import json
import sys
from pathlib import Path

from app.net import clean_host, format_host, format_host_port, ip_version
from app.xray.sg_panel_vless import reality_tcp_link, xhttp_reality_link

HOSTD_ROOT = Path(__file__).resolve().parents[1] / "hostd"
if str(HOSTD_ROOT) not in sys.path:
    sys.path.insert(0, str(HOSTD_ROOT))

from sg_hostd import awg3_runtime  # noqa: E402


def test_host_formatting_preserves_ipv4_and_domains() -> None:
    assert clean_host("example.com.") == "example.com"
    assert ip_version("203.0.113.7") == 4
    assert format_host("203.0.113.7") == "203.0.113.7"
    assert format_host("vpn.example.com") == "vpn.example.com"
    assert format_host_port("203.0.113.7", 443) == "203.0.113.7:443"
    assert format_host_port("vpn.example.com", 443) == "vpn.example.com:443"


def test_host_formatting_brackets_ipv6_literals() -> None:
    assert ip_version("2001:db8::7") == 6
    assert clean_host("[2001:db8::7]") == "2001:db8::7"
    assert format_host("2001:db8::7") == "[2001:db8::7]"
    assert format_host("[2001:db8::7]") == "[2001:db8::7]"
    assert format_host_port("2001:db8::7", 443) == "[2001:db8::7]:443"


def test_reality_tcp_link_uses_ipv6_safe_authority() -> None:
    link = reality_tcp_link(
        uuid="11111111-1111-1111-1111-111111111111",
        host="2001:db8::10",
        port=443,
        title="IPv6 Reality",
        fingerprint="firefox",
        server_name="www.bing.com",
        public_key="public-key",
        short_id="abcd1234",
    )
    assert link.startswith(
        "vless://11111111-1111-1111-1111-111111111111@[2001:db8::10]:443?"
    )


def test_xhttp_reality_link_uses_ipv6_safe_authority() -> None:
    link = xhttp_reality_link(
        uuid="22222222-2222-2222-2222-222222222222",
        host="2001:db8::20",
        port=8444,
        title="IPv6 XHTTP",
        fingerprint="chrome",
        server_name="www.bing.com",
        public_key="public-key",
        short_id="abcd1234",
        path="/sg",
        encryption="mlkem768x25519plus.native.0rtt.sg.test",
    )
    assert link.startswith(
        "vless://22222222-2222-2222-2222-222222222222@[2001:db8::20]:8444?"
    )


def _awg3_secrets() -> dict[str, str]:
    return {
        "SG_GATEWAY_AWG3_PRIVATE_KEY": "server-private",
        "SG_GATEWAY_AWG3_PUBLIC_KEY": "server-public",
        "SG_GATEWAY_AWG3_HEADER_PROTECTION_KEY": "header-key",
        "SG_GATEWAY_AWG3_JC": "4",
        "SG_GATEWAY_AWG3_JMIN": "10",
        "SG_GATEWAY_AWG3_JMAX": "50",
        "SG_GATEWAY_AWG3_S1": "64",
        "SG_GATEWAY_AWG3_S2": "96",
        "SG_GATEWAY_AWG3_S3": "48",
        "SG_GATEWAY_AWG3_S4": "12",
        "SG_GATEWAY_AWG3_H1": "101",
        "SG_GATEWAY_AWG3_H2": "102",
        "SG_GATEWAY_AWG3_H3": "103",
        "SG_GATEWAY_AWG3_H4": "104",
        "SG_GATEWAY_AWG3_CONTENT_PADDING_ADDITION": "10-100",
        "SG_GATEWAY_AWG3_REKEY_AFTER_TIME": "100-120",
        "SG_GATEWAY_AWG3_REKEY_TIMEOUT": "3-7",
        "SG_GATEWAY_AWG3_REJECT_AFTER_TIME": "150-180",
        "SG_GATEWAY_AWG3_KEEPALIVE_TIMEOUT": "5-15",
        "SG_GATEWAY_AWG3_MAX_HANDSHAKE_ATTEMPTS": "15-20",
    }


def _awg3_row(address: str = "10.67.0.2/32") -> dict[str, object]:
    return {
        "client_id": 1,
        "client_name": "Dual Stack",
        "config_json": json.dumps(
            {
                "public_key": "client-public",
                "address": address,
            }
        ),
    }


def test_awg3_ipv4_only_render_keeps_frozen_address_contract(monkeypatch) -> None:
    monkeypatch.setattr(awg3_runtime.cr, "_read_env", lambda _path: {})
    monkeypatch.setattr(awg3_runtime.cr, "_default_interface", lambda: "eth0")

    body = awg3_runtime._render([_awg3_row()], _awg3_secrets())

    assert "Address = 10.67.0.1/16\n" in body
    assert "AllowedIPs = 10.67.0.2/32" in body
    assert "table ip6 sg_gateway_awg3" not in body


def test_awg3_dual_stack_render_adds_stable_ipv6_peer(monkeypatch) -> None:
    monkeypatch.setattr(
        awg3_runtime.cr,
        "_read_env",
        lambda _path: {"SG_GATEWAY_PUBLIC_IPV6": "2606:4700:4700::1111"},
    )
    monkeypatch.setattr(awg3_runtime.cr, "_default_interface", lambda: "eth0")

    network = awg3_runtime._ipv6_network("server-public")
    body = awg3_runtime._render([_awg3_row()], _awg3_secrets())

    assert str(network).startswith("fd")
    assert f"{network.network_address + 1}/64" in body
    assert f"{network.network_address + 2}/128" in body
    assert "AllowedIPs = 10.67.0.2/32," in body
    assert "table ip6 sg_gateway_awg3" in body
    assert f"ip6 saddr {network} masquerade" in body


def test_awg3_userspace_helper_splits_dual_stack_address_line() -> None:
    text = Path("deploy/sg-gateway-awg3-userspace.sh").read_text(encoding="utf-8")
    assert "IFS=',' read -r -a addresses" in text
    assert 'ip -6 address add "$address" dev "$IFACE"' in text
    assert 'ip -4 address add "$address" dev "$IFACE"' in text


def test_all_uri_export_paths_use_ipv6_safe_authorities() -> None:
    text = Path("app/clients/exports.py").read_text(encoding="utf-8")
    assert "from app.net import format_host, format_host_port" in text
    assert "endpoint = format_host_port(host, profile.port)" in text
    assert "authority_host = format_host(host)" in text
    assert 'endpoint = format_host_port(host, int(config.get("port", 9443)))' in text
    assert 'endpoint = format_host_port(host, int(config.get("port", 10443)))' in text
