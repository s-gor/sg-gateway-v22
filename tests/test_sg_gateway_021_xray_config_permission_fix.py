from __future__ import annotations

import json
import stat
from pathlib import Path

from app.routing import runtime, warp_helper


def test_atomic_xray_write_keeps_full_access_permissions(monkeypatch, tmp_path):
    config = tmp_path / "config.json"
    monkeypatch.setenv("SG_GATEWAY_XRAY_CONFIG", str(config))

    runtime.atomic_write_json(config, {"inbounds": [], "outbounds": []}, 0o600)

    assert json.loads(config.read_text(encoding="utf-8"))["inbounds"] == []
    assert stat.S_IMODE(config.stat().st_mode) == 0o777
    assert stat.S_IMODE(config.parent.stat().st_mode) == 0o777


def test_warp_rollback_keeps_xray_config_full_access(monkeypatch, tmp_path):
    config = tmp_path / "config.json"
    monkeypatch.setenv("SG_GATEWAY_XRAY_CONFIG", str(config))

    warp_helper._restore_file(config, b"{}\n", 0o600)

    assert stat.S_IMODE(config.stat().st_mode) == 0o777
    assert stat.S_IMODE(config.parent.stat().st_mode) == 0o777


def test_installer_repairs_xray_permissions_after_warp():
    source = Path("install.sh").read_text(encoding="utf-8")
    assert "SG_GATEWAY_02111_XRAY_FULL_ACCESS_POLICY" in source
    assert "set_xray_config_permissions()" in source
    permission_helper = source.split("set_xray_config_permissions() {", 1)[1].split("\n}", 1)[0]
    assert 'chmod -R 0777 "$root"' in permission_helper
    warp_stage = source.split("stage9_ensure_warp() {", 1)[1].split("\nstage9_start_panel()", 1)[0]
    assert "set_xray_config_permissions" in warp_stage
    assert "systemctl restart xray.service" in warp_stage
    assert "systemctl is-active --quiet xray.service" in warp_stage
