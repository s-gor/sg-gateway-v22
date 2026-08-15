from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from app.xray.profiles import XHTTP_XMUX_RF, _values
from app.xray.sg_panel_vless import xhttp_reality_link

ROOT = Path(__file__).resolve().parents[1]


def test_rf_xmux_values_are_exact():
    assert XHTTP_XMUX_RF == {
        "maxConcurrency": 0,
        "maxConnections": 6,
        "cMaxReuseTimes": 0,
        "hMaxRequestTimes": "600-900",
        "hMaxReusableSecs": "1800-3000",
        "hKeepAlivePeriod": 0,
    }


def test_rf_xmux_is_enabled_by_default_for_both_xhttp_profiles():
    values = _values({}, 443)
    assert values["xhttp_reality_xmux_enabled"] is True
    assert values["xhttp_tls_xmux_enabled"] is True


def test_xhttp_reality_link_contains_url_encoded_json_extra():
    link = xhttp_reality_link(
        uuid="11111111-1111-4111-8111-111111111111",
        host="203.0.113.10",
        port=8444,
        title="XMUX RF",
        fingerprint="firefox",
        server_name="www.microsoft.com",
        public_key="public-key",
        short_id="0123456789abcdef",
        path="/sg-xhttp-reality",
        encryption="mlkem768x25519plus.native.0rtt.example",
        client_mode="stream-one",
        xmux=XHTTP_XMUX_RF,
    )
    query = parse_qs(urlsplit(link).query)
    assert json.loads(query["extra"][0]) == {"xmux": XHTTP_XMUX_RF}


def test_xmux_is_client_only_and_visible_in_connections():
    template = (ROOT / "app/web/templates/connections.html").read_text(encoding="utf-8")
    profiles = (ROOT / "app/xray/profiles.py").read_text(encoding="utf-8")
    inbound = (ROOT / "app/xray/sg_panel_vless.py").read_text(encoding="utf-8")
    exports = (ROOT / "app/clients/exports.py").read_text(encoding="utf-8")

    assert "Клиентский XMUX" in template
    assert "XMUX для РФ" in template
    assert "xps2-xmux-switch" not in template
    assert "_xmux_enabled" not in template
    assert "Показать параметры" in template
    assert "Максимальная параллельность" in template
    for key in (
        "maxConcurrency",
        "maxConnections",
        "cMaxReuseTimes",
        "hMaxRequestTimes",
        "hMaxReusableSecs",
        "hKeepAlivePeriod",
    ):
        assert key in template
        assert key in profiles
    assert '"xmux": dict(xmux)' in inbound
    assert 'query_values["extra"]' in exports
    server_function = inbound.split("def xhttp_reality_inbound", 1)[1].split(
        "def reality_tcp_link", 1
    )[0]
    assert '"xmux"' not in server_function
