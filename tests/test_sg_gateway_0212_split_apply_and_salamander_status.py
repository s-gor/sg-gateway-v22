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

from app.xray import salamander_diagnostics  # noqa: E402
from sg_hostd import client_runtime  # noqa: E402


def test_connections_apply_targets_split_runtime_hostd_command():
    service = (ROOT / "app/mihomo/service.py").read_text(encoding="utf-8")
    block = service[service.index("def apply_candidate("):service.index("def rollback_latest(")]
    assert 'run_hostd_command("mihomo.split.apply"' in block
    assert '_run_helper("apply")' not in block

    commands = (ROOT / "hostd/sg_hostd/commands.py").read_text(encoding="utf-8")
    assert '"mihomo.split.apply": _mihomo_split_apply' in commands
    assert "apply_split_mihomo_singbox_runtime" in commands


def test_candidate_validates_full_form_before_mieru_only_render():
    service = (ROOT / "app/mihomo/service.py").read_text(encoding="utf-8")
    block = service[service.index("def build_candidate("):service.index("def _run_helper(")]
    validate = block.index("_validate_settings(requested_settings, deployments)")
    force_anytls = block.index('settings["anytls_enabled"] = False')
    force_tuic = block.index('settings["tuic_enabled"] = False')
    assert validate < force_anytls < force_tuic


def test_singbox_render_uses_applied_server_ports_and_alpn(monkeypatch):
    monkeypatch.setattr(
        client_runtime,
        "tls_overview",
        lambda: {"https_ready": True, "domain": "vpn.example.com"},
    )
    original_is_file = Path.is_file

    def fake_is_file(path: Path) -> bool:
        value = str(path)
        if value.endswith("/fullchain.pem") or value.endswith("/privkey.pem"):
            return True
        return original_is_file(path)

    monkeypatch.setattr(Path, "is_file", fake_is_file)
    anytls_rows = [
        {
            "client_id": 1,
            "client_name": "A",
            "config_json": json.dumps({"password": "secret", "port": 1111}),
        }
    ]
    tuic_rows = [
        {
            "client_id": 2,
            "client_name": "T",
            "engine_object_id": "11111111-1111-1111-1111-111111111111",
            "config_json": json.dumps(
                {
                    "uuid": "11111111-1111-1111-1111-111111111111",
                    "password": "secret2",
                    "port": 2222,
                }
            ),
        }
    ]
    body = client_runtime._render_singbox_config(
        anytls_rows,
        tuic_rows,
        {
            "anytls_port": 9443,
            "tuic_port": 10443,
            "tuic_congestion_controller": "cubic",
            "tuic_alpn": "h3",
        },
    )
    payload = json.loads(body)
    by_type = {item["type"]: item for item in payload["inbounds"]}
    assert by_type["anytls"]["listen_port"] == 9443
    assert by_type["tuic"]["listen_port"] == 10443
    assert by_type["tuic"]["congestion_control"] == "cubic"
    assert by_type["tuic"]["tls"]["alpn"] == ["h3"]


def test_salamander_diagnostics_uses_safe_hostd_when_xray_config_is_root_only(monkeypatch):
    secret = "S" * 32
    monkeypatch.setattr(
        salamander_diagnostics,
        "get_connection_settings",
        lambda engine: SimpleNamespace(
            config={
                "hysteria2_obfs_mode": "salamander",
                "hysteria2_obfs_password": secret,
            }
        ),
    )
    monkeypatch.setattr(
        salamander_diagnostics,
        "_load_live_config",
        lambda path: ({}, "Xray config is unreadable"),
    )
    monkeypatch.setattr(
        salamander_diagnostics,
        "run_hostd_command",
        lambda command, timeout=5: SimpleNamespace(
            status="ok",
            payload={
                "readable": True,
                "inbound_present": True,
                "finalmask_udp_active": True,
                "live_password_configured": True,
                "password_matches_database": True,
            },
        ),
    )
    result = salamander_diagnostics.inspect()
    assert result["live_config_error"] == ""
    assert result["finalmask_udp_active"] is True
    assert result["password_matches_live"] is True
    assert result["consistent"] is True
    assert secret not in json.dumps(result, ensure_ascii=False)
