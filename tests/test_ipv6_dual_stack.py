from __future__ import annotations

from app.net import clean_host, format_host, format_host_port, ip_version
from app.xray.sg_panel_vless import reality_tcp_link, xhttp_reality_link


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
