from __future__ import annotations

from pathlib import Path


def test_xray_apply_preserves_runtime_without_deployments(monkeypatch, tmp_path):
    from sg_hostd import client_runtime

    monkeypatch.setattr(client_runtime, "init_db", lambda: None)
    monkeypatch.setattr(client_runtime, "_repair_deployment_configs", lambda: None)
    monkeypatch.setattr(client_runtime, "_deployment_rows", lambda engine: [])
    monkeypatch.setattr(client_runtime, "CANDIDATE_DIR", tmp_path / "candidates")
    monkeypatch.setattr(client_runtime, "LOCK_FILE", tmp_path / "apply.lock")
    monkeypatch.setattr(client_runtime.fcntl, "flock", lambda *args: None)
    monkeypatch.setattr(
        client_runtime,
        "_apply_xray",
        lambda: (_ for _ in ()).throw(AssertionError("must not apply empty runtime")),
    )

    result = client_runtime.apply_xray_runtime()
    assert result["ok"] is True
    assert result["clients"] == 0
    assert result["runtime_preserved"] is True


def test_installer_keeps_hostd_error_body():
    installer = Path("install.sh").read_text(encoding="utf-8")
    assert "-w '%{http_code}'" in installer
    assert "sg-hostd xray.apply returned HTTP" in installer
    assert "curl -fsS --max-time 120 -X POST" not in installer
