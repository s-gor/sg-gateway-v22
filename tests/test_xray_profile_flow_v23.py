from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
HOSTD = ROOT / "hostd"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(HOSTD) not in sys.path:
    sys.path.insert(0, str(HOSTD))

from sg_hostd import client_runtime, commands  # noqa: E402


def _profiles() -> dict:
    return {
        "profiles": [
            SimpleNamespace(
                id="reality_tcp", title="VLESS Reality TCP",
                enabled=True, ready=True, tls_required=False,
                port=443, path="",
            ),
            SimpleNamespace(
                id="xhttp_reality", title="VLESS XHTTP Reality",
                enabled=True, ready=True, tls_required=False,
                port=8444, path="/sg-xhttp-reality",
            ),
            SimpleNamespace(
                id="xhttp_tls", title="VLESS XHTTP TLS",
                enabled=False, ready=False, tls_required=True,
                port=8445, path="/sg-xhttp-tls",
            ),
            SimpleNamespace(
                id="hysteria2", title="Hysteria 2",
                enabled=False, ready=False, tls_required=True,
                port=8446, path="",
            ),
        ],
        "tls_ready": False,
        "tls_domain": "",
    }


def test_selected_server_profiles_render_without_clients(monkeypatch):
    monkeypatch.setattr(
        client_runtime,
        "_read_env",
        lambda path: {
            "SG_GATEWAY_XRAY_PRIVATE_KEY": "private-key",
            "SG_GATEWAY_XRAY_SHORT_ID": "0123456789abcdef",
            "SG_GATEWAY_VLESS_ENCRYPTION": "mlkem768x25519plus.native.0rtt.100-111-1111.75-0-111.50-0-3333.Q0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0M",
            "SG_GATEWAY_VLESS_DECRYPTION": "mlkem768x25519plus.native.600s.100-111-1111.75-0-111.50-0-3333.U1NTU1NTU1NTU1NTU1NTU1NTU1NTU1NTU1NTU1NTU1NTU1NTU1NTU1NTU1NTU1NTU1NTU1NTU1NTU1NTU1NTUw",
            "SG_GATEWAY_REALITY_SNI": "www.bing.com",
            "SG_GATEWAY_REALITY_TARGET": "www.bing.com:443",
        },
    )
    monkeypatch.setattr(
        client_runtime,
        "get_connection_settings",
        lambda engine: SimpleNamespace(
            config={"server_name": "www.bing.com", "target": "www.bing.com:443"},
            host="203.0.113.10",
            port=443,
        ),
    )
    monkeypatch.setattr(client_runtime, "xray_profiles_overview", _profiles)

    config = json.loads(client_runtime._render_xray_config([]))
    assert [item["tag"] for item in config["inbounds"]] == [
        "sg-vless-reality-tcp",
        "sg-vless-xhttp-reality",
    ]
    assert config["inbounds"][0]["settings"]["clients"] == []
    assert config["inbounds"][1]["settings"]["clients"] == []
    assert config["inbounds"][1]["settings"]["decryption"] == "mlkem768x25519plus.native.600s.100-111-1111.75-0-111.50-0-3333.U1NTU1NTU1NTU1NTU1NTU1NTU1NTU1NTU1NTU1NTU1NTU1NTU1NTU1NTU1NTU1NTU1NTU1NTU1NTU1NTU1NTUw"


def test_xray_test_command_uses_candidate_renderer(monkeypatch):
    monkeypatch.setattr(
        commands,
        "test_xray_candidate",
        lambda: {"ok": True, "message": "candidate ok", "candidate": "/tmp/test.json"},
    )
    result = commands.execute_command("xray.test")
    assert result.status == "ok"
    assert result.message == "candidate ok"
    assert result.payload["candidate"] == "/tmp/test.json"


def test_connections_template_has_only_check_and_apply_actions():
    template = (ROOT / "app/web/templates/connections.html").read_text(encoding="utf-8")
    assert template.count('name="action" value="test"') == 1
    assert template.count('name="action" value="apply"') >= 1  # Mihomo has its own apply action.
    xray_start = template.index('id="xray-profiles"')
    xray_end = template.index('<details class="cnv1-advanced', xray_start)
    xray = template[xray_start:xray_end]
    assert xray.count('name="action" value="test"') == 1
    assert xray.count('name="action" value="apply"') == 1
    assert "Сохранить Xray-профили" not in xray
    assert "Открыть терминал" not in xray
    assert "ЭТАП 1" not in xray


def test_preview24_final_css_is_loaded_last():
    base = (ROOT / "app/web/templates/base.html").read_text(encoding="utf-8")
    assert base.index("sg-preview28-final.css") > base.index("sg-luxury-jade-depth-v2.css")
    css = (ROOT / "app/web/static/sg-preview28-final.css").read_text(encoding="utf-8")
    assert "border-color: transparent !important" in css
    assert ".sv1-summary.sg-ljd-system-summary" in css
