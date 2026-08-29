from __future__ import annotations

import subprocess
from pathlib import Path
from types import SimpleNamespace

from app.maintenance import panel_updates
from sg_hostd import operation_jobs, panel_update_runtime


ROOT = Path(__file__).resolve().parents[1]


def test_update_channel_defaults_are_consistent_and_old_repo_is_gone() -> None:
    assert panel_updates.GITHUB_REPO == "s-gor/sg-gateway-v22"
    # Stable releases track the immutable stable-02206 channel by default.
    assert panel_updates.GITHUB_BRANCH == "stable-02206"
    update = (ROOT / "deploy" / "update-from-github.sh").read_text(encoding="utf-8")
    bootstrap = (ROOT / "deploy" / "install-from-github.sh").read_text(encoding="utf-8")
    assert 'REPOSITORY="s-gor/sg-gateway-v22"' in update
    assert '${SG_GATEWAY_GITHUB_BRANCH:-${SG_GATEWAY_UPDATE_BRANCH:-stable-02206}}' in update
    assert "stable-02206" in bootstrap
    assert "SG_GATEWAY_ALLOW_DEVELOPMENT" not in bootstrap
    assert "raw.githubusercontent.com/%s/%s/deploy/update-from-github.sh" in bootstrap
    assert "sudo env SG_GATEWAY_GITHUB_BRANCH=%s bash" in bootstrap
    assert "raw.githubusercontent.com/s-gor/sg-gateway/main/deploy/update-from-github.sh" not in bootstrap
    assert 'REPOSITORY="s-gor/sg-gateway"' not in update
    assert "dev-02205" not in update


def test_overview_queries_configured_channel_not_main(monkeypatch) -> None:
    seen = []
    monkeypatch.setattr(panel_updates, "GITHUB_REPO", "s-gor/sg-gateway-v22")
    monkeypatch.setattr(panel_updates, "GITHUB_API", "https://api.github.test/repos/s-gor/sg-gateway-v22")
    monkeypatch.setattr(panel_updates, "GITHUB_BRANCH", "dev-v22")

    def fake_json(url: str, timeout: float = 8.0):
        seen.append(url)
        return {"sha": "a" * 40, "commit": {"author": {"date": "2026-08-16T00:00:00Z"}}, "html_url": "x"}

    monkeypatch.setattr(panel_updates, "_request_json", fake_json)
    sha, _, _ = panel_updates._latest_channel()
    assert sha == "a" * 40
    assert seen == ["https://api.github.test/repos/s-gor/sg-gateway-v22/commits/dev-v22"]


def test_02204_without_baseline_can_bootstrap_to_stable_02206(monkeypatch) -> None:
    monkeypatch.setattr(panel_updates, "_CACHE", None)
    monkeypatch.setattr(panel_updates, "_read_state", lambda: {})
    monkeypatch.setattr(panel_updates, "source_fingerprint", lambda: "local-fingerprint")
    monkeypatch.setattr(panel_updates, "get_version", lambda: "0.1.0-022.04")
    monkeypatch.setattr(
        panel_updates,
        "_latest_channel",
        lambda: ("b" * 40, "2026-08-19T00:00:00Z", "https://github.test/commit"),
    )
    monkeypatch.setattr(panel_updates, "_remote_version", lambda commit: "0.1.0-022.06")

    result = panel_updates.overview(refresh=True)

    assert result["installed_version"] == "0.1.0-022.04"
    assert result["latest_version"] == "0.1.0-022.06"
    assert result["state"] == "available"
    assert result["can_install"] is True
    assert result["bootstrap_allowed"] is True


def test_operation_job_passes_explicit_channel_to_safe_shell_updater(tmp_path, monkeypatch) -> None:
    script = tmp_path / "update-from-github.sh"
    script.write_text("#!/bin/bash\n", encoding="utf-8")
    monkeypatch.setattr(operation_jobs, "PANEL_UPDATE_SCRIPT", script)
    monkeypatch.setattr(operation_jobs, "GITHUB_BRANCH", "dev-v22")
    captured = {}

    def fake_start(kind, title, target_url, back_url, extra=None, *, command=None):
        captured.update(kind=kind, title=title, extra=extra, command=command)
        return {"ok": True}

    monkeypatch.setattr(operation_jobs, "_start", fake_start)
    operation_jobs.start_panel_update_job()
    assert captured["kind"] == "panel_update_channel"
    assert captured["title"] == "Безопасное обновление SG-Gateway из GitHub"
    assert captured["extra"]["channel"] == "dev-v22"
    assert captured["command"][:2] == ("/usr/bin/env", "SG_GATEWAY_GITHUB_BRANCH=dev-v22")
    assert captured["command"][-2:] == ("/bin/bash", str(script))


def test_python_runtime_delegates_to_shell_with_channel(tmp_path, monkeypatch) -> None:
    root = tmp_path / "live"
    script = root / "deploy" / "update-from-github.sh"
    script.parent.mkdir(parents=True)
    script.write_text("#!/bin/bash\n", encoding="utf-8")
    (root / "VERSION").write_text("0.1.0-021.12\n", encoding="utf-8")
    monkeypatch.setattr(panel_update_runtime, "LIVE_ROOT", root)
    monkeypatch.setattr(panel_update_runtime, "GITHUB_BRANCH", "dev-v22")
    calls = []

    def fake_run(args, **kwargs):
        calls.append((args, kwargs))
        return SimpleNamespace(returncode=0, stdout="ok", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    result = panel_update_runtime.update_panel()
    assert result["ok"] is True
    assert result["channel"] == "dev-v22"
    args, kwargs = calls[0]
    assert args == ["/bin/bash", str(script)]
    assert kwargs["env"]["SG_GATEWAY_GITHUB_BRANCH"] == "dev-v22"


def test_staged_validation_and_shell_fallback_use_production_wsgi() -> None:
    runtime = (ROOT / "hostd" / "sg_hostd" / "panel_update_runtime.py").read_text(encoding="utf-8")
    update = (ROOT / "deploy" / "update-from-github.sh").read_text(encoding="utf-8")
    assert '"app/production.py"' in runtime
    assert "import app.production; import sg_hostd.commands" in runtime
    assert 'PANEL_PRODUCTION_WSGI="app.production:app"' in update
    assert 'printf \'%s\\n\' "$PANEL_PRODUCTION_WSGI"' in update
    assert "migrate_panel_wsgi_service()" in update
    assert '[[ -f "$SOURCE_DIR/app/production.py" ]]' in update
    assert "wsgi-validation" in runtime
    assert 'env["SG_GATEWAY_DATA_DIR"] = str(validation_root / "data")' in runtime
    assert 'env["SG_GATEWAY_LOG_DIR"] = str(validation_root / "log")' in runtime
