from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parents[1]
HOSTD = ROOT / "hostd"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(HOSTD) not in sys.path:
    sys.path.insert(0, str(HOSTD))

from app.clients import exports
from app.clients.repository import Client
from app.xray.profiles import REALITY_TCP_FLOW
from sg_hostd import client_runtime


def test_half_width_cards_have_equal_height():
    css = (ROOT / "app/web/static/sg-preview28-final.css").read_text(encoding="utf-8")
    assert ".cnv1-engine-pair { align-items: stretch; }" in css
    assert "height: auto; align-self: stretch;" in css
    assert ".cnv1-engine-awg .cnv1-engine-form-compact { flex: 1 1 auto; }" in css


def test_vision_is_explicit_in_connections_ui():
    template = (ROOT / "app/web/templates/connections.html").read_text(encoding="utf-8")
    assert "XTLS VISION" in template
    assert "{{ profile.flow }}" in template
    assert "Vision · {{ profile.flow }}" in template
    assert "VLESS Encryption ·" in template
    assert "Обязательный XTLS Vision для выбранного VLESS-профиля" not in template


def _profiles():
    return {
        "profiles": [
            SimpleNamespace(id="reality_tcp", title="VLESS Reality TCP", enabled=True, ready=True, tls_required=False, port=443, path="", flow=REALITY_TCP_FLOW),
            SimpleNamespace(id="xhttp_reality", title="VLESS XHTTP Reality", enabled=True, ready=True, tls_required=False, port=8444, path="/sg-xhttp-reality", flow=REALITY_TCP_FLOW),
            SimpleNamespace(id="xhttp_tls", title="VLESS XHTTP TLS", enabled=False, ready=False, tls_required=True, port=8445, path="/sg-xhttp-tls", flow=REALITY_TCP_FLOW),
            SimpleNamespace(id="hysteria2", title="Hysteria 2", enabled=False, ready=False, tls_required=True, port=8446, path="", flow=""),
        ],
        "tls_ready": False,
        "tls_domain": "",
    }


def test_runtime_candidate_contains_vision_for_reality_tcp(monkeypatch):
    monkeypatch.setattr(client_runtime, "_read_env", lambda path: {
        "SG_GATEWAY_XRAY_PRIVATE_KEY": "private-key",
        "SG_GATEWAY_XRAY_SHORT_ID": "0123456789abcdef",
        "SG_GATEWAY_VLESS_ENCRYPTION": "mlkem768x25519plus.native.0rtt.100-111-1111.75-0-111.50-0-3333.Q0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0M",
            "SG_GATEWAY_VLESS_DECRYPTION": "mlkem768x25519plus.native.600s.100-111-1111.75-0-111.50-0-3333.U1NTU1NTU1NTU1NTU1NTU1NTU1NTU1NTU1NTU1NTU1NTU1NTU1NTU1NTU1NTU1NTU1NTU1NTU1NTU1NTU1NTUw",
        "SG_GATEWAY_REALITY_SNI": "www.bing.com",
        "SG_GATEWAY_REALITY_TARGET": "www.bing.com:443",
    })
    monkeypatch.setattr(client_runtime, "get_connection_settings", lambda engine: SimpleNamespace(
        config={"server_name": "www.bing.com", "target": "www.bing.com:443"}, host="203.0.113.10", port=443,
    ))
    monkeypatch.setattr(client_runtime, "xray_profiles_overview", _profiles)
    row = {
        "client_id": 1,
        "client_name": "Vision Test",
        "engine_object_id": "11111111-1111-1111-1111-111111111111",
        "config_json": json.dumps({"uuid": "11111111-1111-1111-1111-111111111111", "profiles": ["reality_tcp"]}),
    }
    config = json.loads(client_runtime._render_xray_config([row]))
    client = config["inbounds"][0]["settings"]["clients"][0]
    assert client["flow"] == REALITY_TCP_FLOW


def test_client_link_contains_same_vision_flow(monkeypatch):
    client = Client(id=1, name="Vision Test", enabled=True, expires_at=None, awg_status="missing", xray_status="applied")
    deployment = SimpleNamespace(engine="xray", status="applied", config_json=json.dumps({
        "host": "203.0.113.10",
        "uuid": "11111111-1111-1111-1111-111111111111",
        "fingerprint": "firefox",
        "server_name": "www.bing.com",
        "public_key": "public-key",
        "short_id": "0123456789abcdef",
        "profiles": ["reality_tcp"],
    }))
    monkeypatch.setattr(exports, "list_client_deployments", lambda client_id: [deployment])
    monkeypatch.setattr(exports, "xray_profiles_overview", _profiles)
    result = exports.build_xray_profile_link(client, "reality_tcp")
    query = parse_qs(urlparse(result.body).query)
    assert query["flow"] == [REALITY_TCP_FLOW]


def test_xray_is_above_equal_height_awg_mihomo_pair():
    template = (ROOT / "app/web/templates/connections.html").read_text(encoding="utf-8")
    xray = template.index('class="cnv1-engines cnv1-xray-row"')
    pair = template.index('class="cnv1-engine-pair"')
    note = template.index('class="cnv1-note-panel sg-ljd-card"')
    assert xray < pair < note


def test_awg_and_mihomo_still_share_one_equal_height_row():
    template = (ROOT / "app/web/templates/connections.html").read_text(encoding="utf-8")
    pair_start = template.index('<section class="cnv1-engine-pair">')
    pair_end = template.index('</section>', template.index('{% include "_mihomo_panel.html" %}', pair_start))
    pair = template[pair_start:pair_end]
    assert 'class="cnv1-engine-card cnv1-engine-awg' in pair
    assert '{% include "_mihomo_panel.html" %}' in pair
    css = (ROOT / "app/web/static/sg-preview28-final.css").read_text(encoding="utf-8")
    assert '.cnv1-engine-pair { align-items: stretch; }' in css
    assert 'height: auto; align-self: stretch;' in css
    assert '.cnv1-engine-awg .cnv1-form-actions { margin-top: auto; }' in css
    assert '.cnv1-engine-mihomo .mhv2-actions' in css
    assert 'margin-top: auto;' in css
