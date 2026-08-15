from __future__ import annotations

from pathlib import Path

from app.maintenance import core_updates, panel_updates


ROOT = Path(__file__).resolve().parents[1]


def test_panel_update_overview_pins_exact_main_commit_but_blocks_unbound_baseline(monkeypatch, tmp_path):
    commit = "a" * 40
    monkeypatch.setattr(panel_updates, "STATE_FILE", tmp_path / "state.json")
    monkeypatch.setattr(panel_updates, "source_fingerprint", lambda: "f" * 64)
    monkeypatch.setattr(panel_updates, "_remote_version", lambda sha: "0.1.0-021")
    monkeypatch.setattr(
        panel_updates,
        "_request_json",
        lambda url, timeout=8.0: {
            "sha": commit,
            "html_url": "https://example.invalid/commit",
            "commit": {"author": {"date": "2026-07-29T00:00:00Z"}},
        },
    )
    panel_updates._CACHE = None
    result = panel_updates.overview(refresh=True)
    assert result["latest_commit"] == commit
    assert result["latest_short"] == "aaaaaaaa"
    assert result["state"] == "uninitialized"
    assert result["can_install"] is False


def test_panel_update_state_marks_exact_commit_current(monkeypatch, tmp_path):
    commit = "b" * 40
    state = tmp_path / "state.json"
    fingerprint = "e" * 64
    state.write_text('{"commit":"' + commit + '","source_fingerprint":"' + fingerprint + '"}', encoding="utf-8")
    monkeypatch.setattr(panel_updates, "STATE_FILE", state)
    monkeypatch.setattr(panel_updates, "source_fingerprint", lambda: fingerprint)
    monkeypatch.setattr(panel_updates, "_remote_version", lambda sha: "0.1.0-021.4")
    monkeypatch.setattr(
        panel_updates,
        "_request_json",
        lambda url, timeout=8.0: {"sha": commit, "commit": {"author": {"date": ""}}},
    )
    panel_updates._CACHE = None
    result = panel_updates.overview(refresh=True)
    assert result["state"] == "current"
    assert result["can_install"] is False


def test_core_version_parser_handles_real_outputs():
    assert core_updates._parse_version("Mihomo Meta v1.19.29 linux amd64") == "1.19.29"
    assert core_updates._parse_version("sing-box version 1.13.14") == "1.13.14"
    assert core_updates._parse_version("wgcf-cli version v0.3.6") == "0.3.6"
    assert core_updates._parse_version("wgcf-cli version \x1b[1;36mv0.3.6\x1b[0m") == "0.3.6"


def test_update_ui_has_three_independent_sections():
    template = (ROOT / "app/web/templates/maintenance.html").read_text(encoding="utf-8")
    assert "SG-GATEWAY UPDATE" in template
    assert "OTHER CORES" in template
    assert "GEOFILES UPDATE" in template
    assert "Обновить всё" not in template
    assert "panel_update_start" in template
    assert "core_update_start" in template


def test_hostd_allowlist_and_runners_include_panel_and_core_updates():
    commands = (ROOT / "hostd/sg_hostd/commands.py").read_text(encoding="utf-8")
    runner = (ROOT / "hostd/sg_hostd/operation_job_runner.py").read_text(encoding="utf-8")
    for marker in (
        '"panel.update.start"',
        '"core.update.mihomo.start"',
        '"core.update.sing-box.start"',
        '"core.update.wgcf.start"',
    ):
        assert marker in commands
    assert "run_panel_update" in runner
    assert "run_core_update" in runner


def test_panel_runtime_blocks_dependency_changes_and_has_rollback():
    runtime = (ROOT / "hostd/sg_hostd/panel_update_runtime.py").read_text(encoding="utf-8")
    assert "requirements.txt изменён" in runtime
    assert "_backup_live" in runtime
    assert "_deploy_source(backup)" in runtime
    assert "commits/main" in runtime
    assert "archive/{commit}.tar.gz" in runtime
    assert ".venv" in runtime
    assert "_baseline_mode" in runtime
    assert "Автоматическое обновление сейчас недоступно." in runtime
    assert "локальный исходник не совпадает" not in runtime


def test_core_runtime_requires_official_digest_and_atomic_replace():
    runtime = (ROOT / "hostd/sg_hostd/core_update_runtime.py").read_text(encoding="utf-8")
    assert "GitHub Release не предоставил официальный SHA-256" in runtime
    assert "os.replace(replacement, binary)" in runtime
    assert "_restore(binary, backup" in runtime
    assert "Понижение" in runtime


def test_geofiles_apply_has_space_backup_and_stop_before_switch():
    source = (ROOT / "app/routing/geofiles.py").read_text(encoding="utf-8")
    apply_block = source[source.index("def root_apply_candidate"):source.index("def root_rollback_latest")]
    assert "_ensure_apply_free_space(candidate, asset)" in apply_block
    assert "_verify_backup" in source
    assert "_stop_xray_for_switch()" in apply_block
    assert "_start_xray_after_switch()" in apply_block
    assert "xray_test_config" in apply_block


def test_core_update_template_indexes_items_key_not_dict_method():
    template = (ROOT / "app/web/templates/maintenance.html").read_text(encoding="utf-8")
    assert 'core_updates["items"]' in template
    assert "core_updates.items if core_updates" not in template


def test_panel_update_bootstrap_allows_strictly_newer_version_without_state(monkeypatch, tmp_path):
    commit = "c" * 40
    monkeypatch.setattr(panel_updates, "STATE_FILE", tmp_path / "missing-state.json")
    monkeypatch.setattr(panel_updates, "source_fingerprint", lambda: "f" * 64)
    monkeypatch.setattr(panel_updates, "get_version", lambda: "0.1.0-021")
    monkeypatch.setattr(panel_updates, "_latest_main", lambda: (commit, "2026-07-30T00:00:00Z", "https://example.invalid/commit"))
    monkeypatch.setattr(panel_updates, "_remote_version", lambda sha: "0.1.0-021.4")
    panel_updates._CACHE = None
    result = panel_updates.overview(refresh=True)
    assert result["latest_commit"] == commit
    assert result["latest_version"] == "0.1.0-021.4"
    assert result["bootstrap_allowed"] is True
    assert result["can_install"] is True
    assert result["state"] == "available"
    assert result["message"] == "Доступна VERSION 0.1.0-021.4. Можно выполнить безопасное обновление SG-Gateway."
    assert "baseline" not in result["message"].lower()


def test_panel_update_bootstrap_does_not_allow_same_version(monkeypatch, tmp_path):
    commit = "d" * 40
    monkeypatch.setattr(panel_updates, "STATE_FILE", tmp_path / "missing-state.json")
    monkeypatch.setattr(panel_updates, "source_fingerprint", lambda: "f" * 64)
    monkeypatch.setattr(panel_updates, "get_version", lambda: "0.1.0-021.4")
    monkeypatch.setattr(panel_updates, "_latest_main", lambda: (commit, "", ""))
    monkeypatch.setattr(panel_updates, "_remote_version", lambda sha: "0.1.0-021.4")
    panel_updates._CACHE = None
    result = panel_updates.overview(refresh=True)
    assert result["bootstrap_allowed"] is False
    assert result["can_install"] is False
    assert result["state"] == "uninitialized"


def test_panel_runtime_has_bootstrap_path_and_atom_fallback():
    runtime = (ROOT / "hostd/sg_hostd/panel_update_runtime.py").read_text(encoding="utf-8")
    assert "def _baseline_mode" in runtime
    assert 'return "bootstrap", {}' in runtime
    assert "строго более новую VERSION" in runtime
    assert "updater-baseline" not in runtime
    assert "commits/main.atom" in runtime
