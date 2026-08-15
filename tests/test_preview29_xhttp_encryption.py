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
from sg_hostd import client_runtime, commands

ENCRYPTION = "mlkem768x25519plus.native.0rtt.100-111-1111.75-0-111.50-0-3333.Q0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0M"
DECRYPTION = "mlkem768x25519plus.native.600s.100-111-1111.75-0-111.50-0-3333.U1NTU1NTU1NTU1NTU1NTU1NTU1NTU1NTU1NTU1NTU1NTU1NTU1NTU1NTU1NTU1NTU1NTU1NTU1NTU1NTU1NTUw"
UUID = "11111111-1111-1111-1111-111111111111"


def _profiles():
    return {
        "profiles": [
            SimpleNamespace(id="reality_tcp", title="VLESS Reality TCP", enabled=True, ready=True, tls_required=False, port=443, path="", flow=REALITY_TCP_FLOW, encryption_required=False, encryption_ready=False),
            SimpleNamespace(id="xhttp_reality", title="VLESS XHTTP Reality", enabled=True, ready=True, tls_required=False, port=8444, path="/sg-xhttp-reality", flow=REALITY_TCP_FLOW, encryption_required=True, encryption_ready=True),
            SimpleNamespace(id="xhttp_tls", title="VLESS XHTTP TLS", enabled=False, ready=False, tls_required=True, port=8445, path="/sg-xhttp-tls", flow=REALITY_TCP_FLOW, encryption_required=True, encryption_ready=True),
            SimpleNamespace(id="hysteria2", title="Hysteria 2", enabled=False, ready=False, tls_required=True, port=8446, path="", flow="", encryption_required=False, encryption_ready=False),
        ],
        "tls_ready": False,
        "tls_domain": "",
        "host": "203.0.113.10",
    }


def test_xhttp_runtime_uses_vision_and_server_decryption(monkeypatch):
    monkeypatch.setattr(client_runtime, "_read_env", lambda path: {
        "SG_GATEWAY_XRAY_PRIVATE_KEY": "private-key",
        "SG_GATEWAY_XRAY_SHORT_ID": "0123456789abcdef",
        "SG_GATEWAY_VLESS_ENCRYPTION": ENCRYPTION,
        "SG_GATEWAY_VLESS_DECRYPTION": DECRYPTION,
        "SG_GATEWAY_REALITY_SNI": "www.bing.com",
        "SG_GATEWAY_REALITY_TARGET": "www.bing.com:443",
    })
    monkeypatch.setattr(client_runtime, "get_connection_settings", lambda engine: SimpleNamespace(
        config={"server_name": "www.bing.com", "target": "www.bing.com:443"},
        host="203.0.113.10",
        port=443,
    ))
    monkeypatch.setattr(client_runtime, "xray_profiles_overview", _profiles)
    row = {
        "client_id": 1,
        "client_name": "XHTTP Test",
        "engine_object_id": UUID,
        "config_json": json.dumps({"uuid": UUID, "profiles": ["xhttp_reality"]}),
    }
    config = json.loads(client_runtime._render_xray_config([row]))
    inbound = next(item for item in config["inbounds"] if item["tag"] == "sg-vless-xhttp-reality")
    assert inbound["settings"]["decryption"] == DECRYPTION
    assert inbound["settings"]["clients"][0]["flow"] == REALITY_TCP_FLOW
    assert inbound["streamSettings"]["network"] == "xhttp"
    assert "method" not in inbound["streamSettings"]


def test_xhttp_link_contains_client_encryption_and_vision(monkeypatch):
    client = Client(id=1, name="XHTTP Test", enabled=True, expires_at=None, awg_status="missing", xray_status="applied")
    deployment = SimpleNamespace(engine="xray", status="applied", config_json=json.dumps({
        "host": "203.0.113.10",
        "uuid": UUID,
        "fingerprint": "firefox",
        "server_name": "www.bing.com",
        "public_key": "public-key",
        "short_id": "0123456789abcdef",
        "vless_encryption": ENCRYPTION,
        "profiles": ["xhttp_reality"],
    }))
    monkeypatch.setattr(exports, "list_client_deployments", lambda client_id: [deployment])
    monkeypatch.setattr(exports, "xray_profiles_overview", _profiles)
    result = exports.build_xray_profile_link(client, "xhttp_reality")
    query = parse_qs(urlparse(result.body).query)
    assert query["type"] == ["xhttp"]
    assert query["flow"] == [REALITY_TCP_FLOW]
    assert query["encryption"] == [ENCRYPTION]


def test_xhttp_link_is_not_exported_without_encryption(monkeypatch):
    client = Client(id=1, name="XHTTP Test", enabled=True, expires_at=None, awg_status="missing", xray_status="applied")
    deployment = SimpleNamespace(engine="xray", status="applied", config_json=json.dumps({
        "host": "203.0.113.10", "uuid": UUID, "profiles": ["xhttp_reality"]
    }))
    monkeypatch.setattr(exports, "list_client_deployments", lambda client_id: [deployment])
    monkeypatch.setattr(exports, "xray_profiles_overview", _profiles)
    assert exports.build_xray_profile_link(client, "xhttp_reality").body == ""


def test_hostd_exposes_synchronous_xray_apply(monkeypatch):
    monkeypatch.setattr(commands, "apply_xray_runtime", lambda: {
        "ok": True, "message": "Xray applied", "engine": "xray", "clients": 2
    })
    result = commands.execute_command("xray.apply")
    assert result.status == "ok"
    assert result.payload["engine"] == "xray"
    assert result.payload["clients"] == 2


def test_installer_builds_full_pair_from_mlkem768_output(tmp_path):
    import os
    import subprocess

    seed = DECRYPTION.rsplit(".", 1)[-1]
    client_key = ENCRYPTION.rsplit(".", 1)[-1]
    fake = tmp_path / "xray"
    fake.write_text(
        "#!/usr/bin/env bash\n"
        "if [[ \"$1\" == \"mlkem768\" ]]; then\n"
        f"  printf 'Seed: %s\\nClient: %s\\n' '{seed}' '{client_key}'\n"
        "else\n"
        "  exit 1\n"
        "fi\n",
        encoding="utf-8",
    )
    fake.chmod(0o755)
    env = dict(os.environ)
    env["PATH"] = f"{tmp_path}:{env.get('PATH', '')}"
    result = subprocess.run(
        ["bash", "-c", f"source {ROOT / 'install.sh'}; generate_vless_pair"],
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )
    assert result.stdout.splitlines() == [ENCRYPTION, DECRYPTION]
