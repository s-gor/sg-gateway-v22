from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
HOSTD = ROOT / "hostd"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(HOSTD) not in sys.path:
    sys.path.insert(0, str(HOSTD))

from app.maintenance import xray_updates
from app.xray import profiles
from sg_hostd import client_runtime, xray_update_runtime
from sg_hostd.commands import list_allowed_commands


def test_version_comparison_is_numeric():
    assert xray_updates.compare_versions("26.7.11", "26.6.27") == 1
    assert xray_updates.compare_versions("v26.6.27", "26.6.27") == 0
    assert xray_updates.compare_versions("26.3.27", "26.6.27") == -1


def test_channel_state_blocks_downgrade_and_allows_upgrade():
    stable = xray_updates.XrayRelease(
        channel="stable",
        version="26.3.27",
        tag="v26.3.27",
        published_at="2026-03-27T00:00:00Z",
        prerelease=False,
        html_url="https://example.invalid/stable",
    )
    prerelease = xray_updates.XrayRelease(
        channel="prerelease",
        version="26.7.11",
        tag="v26.7.11",
        published_at="2026-07-11T00:00:00Z",
        prerelease=True,
        html_url="https://example.invalid/prerelease",
    )
    stable_state = xray_updates._channel_state("26.6.27", stable)
    prerelease_state = xray_updates._channel_state("26.6.27", prerelease)
    assert stable_state["state"] == "blocked"
    assert stable_state["can_install"] is False
    assert prerelease_state["state"] == "available"
    assert prerelease_state["can_install"] is True


def test_profiles_accept_newer_xray_and_reject_older():
    assert profiles._version_supported("26.9.9") is True
    assert profiles._version_supported("26.10.1") is True
    assert profiles._version_supported("26.9.8") is False
    assert profiles._version_supported("26.7.28") is False


def test_hostd_minimum_policy_accepts_newer(monkeypatch):
    monkeypatch.setattr(
        client_runtime,
        "_run",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            args=["xray", "version"], returncode=0, stdout="Xray 26.9.9 test\n", stderr=""
        ),
    )
    assert client_runtime._require_xray_version() == "26.9.9"


def test_xray_updater_allows_recovery_upgrade_from_installed_below_minimum(monkeypatch, tmp_path):
    monkeypatch.setattr(xray_update_runtime, "LOCK_FILE", tmp_path / "xray-update.lock")
    monkeypatch.setattr(xray_update_runtime, "_installed_version", lambda *args, **kwargs: "26.6.27")
    monkeypatch.setattr(
        xray_update_runtime,
        "_latest_release",
        lambda channel: {"tag_name": "v26.9.9"},
    )

    def reached_asset_stage():
        raise RuntimeError("reached-asset-stage")

    monkeypatch.setattr(xray_update_runtime, "_asset_filename", reached_asset_stage)

    with pytest.raises(RuntimeError, match="reached-asset-stage"):
        xray_update_runtime.update_xray("prerelease")


def test_xray_updater_rejects_target_below_minimum_even_during_recovery(monkeypatch, tmp_path):
    monkeypatch.setattr(xray_update_runtime, "LOCK_FILE", tmp_path / "xray-update.lock")
    monkeypatch.setattr(xray_update_runtime, "_installed_version", lambda *args, **kwargs: "26.6.27")
    monkeypatch.setattr(
        xray_update_runtime,
        "_latest_release",
        lambda channel: {"tag_name": "v26.7.11"},
    )

    with pytest.raises(
        xray_update_runtime.XrayUpdateRuntimeError,
        match="целевая версия Xray v26.7.11 ниже минимально поддерживаемой v26.9.9",
    ):
        xray_update_runtime.update_xray("prerelease")


def test_update_commands_are_explicitly_allowlisted():
    commands = list_allowed_commands()
    assert "xray.update.stable.start" in commands
    assert "xray.update.prerelease.start" in commands


def test_installer_bootstraps_26627_but_preserves_supported_newer():
    installer = (ROOT / "install.sh").read_text(encoding="utf-8")
    assert 'XRAY_REQUIRED_VERSION="v26.9.9"' in installer
    assert 'XRAY_MINIMUM_VERSION="v26.9.9"' in installer
    assert "install_xray_from_vendor" in installer
    assert 'XRAY_VENDOR_FILE="Xray-linux-64.zip"' in installer
    assert 'dpkg --compare-versions "${installed_xray#v}" ge "${XRAY_MINIMUM_VERSION#v}"' in installer
    assert "Сохраняю установленный Xray" in installer


def test_manifest_and_updates_ui_declare_safe_update_flow():
    manifest = json.loads((ROOT / "release-manifest.json").read_text(encoding="utf-8"))
    template = (ROOT / "app/web/templates/maintenance.html").read_text(encoding="utf-8")
    runtime = (ROOT / "hostd/sg_hostd/xray_update_runtime.py").read_text(encoding="utf-8")
    version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    assert manifest["version"] == version
    assert manifest["xray"]["minimum_version"] == "v26.9.9"
    assert manifest["xray"]["required_version"] == "v26.9.9"
    assert manifest["xray"]["updates"]["automatic_rollback"] is True
    assert "Backups" in template and "Updates" in template
    assert "Стабильная версия" in template
    assert "Предварительная версия" in template
    assert "Понижение запрещено" in template
    assert "SHA-256" in template
    assert "_restore_binary" in runtime
    assert '"systemctl", "restart", "xray.service"' in runtime


def test_recovery_upgrade_regenerates_config_before_testing_new_binary(monkeypatch, tmp_path):
    binary = tmp_path / "xray"
    config = tmp_path / "config.json"
    update_root = tmp_path / "updates"
    binary.write_text("old-binary", encoding="utf-8")
    config.write_text("old-config", encoding="utf-8")

    monkeypatch.setattr(xray_update_runtime, "XRAY_BINARY", binary)
    monkeypatch.setattr(xray_update_runtime, "XRAY_CONFIG", config)
    monkeypatch.setattr(xray_update_runtime, "UPDATE_ROOT", update_root)
    monkeypatch.setattr(xray_update_runtime, "BACKUP_DIR", update_root / "backups")
    monkeypatch.setattr(xray_update_runtime, "LOCK_FILE", tmp_path / "xray-update.lock")
    monkeypatch.setattr(xray_update_runtime, "LAST_RESULT", update_root / "last-update.json")
    monkeypatch.setattr(
        xray_update_runtime,
        "_latest_release",
        lambda channel: {
            "tag_name": "v26.9.9",
            "assets": [{"name": "Xray-linux-64.zip", "browser_download_url": "https://example.invalid/xray.zip"}],
        },
    )
    monkeypatch.setattr(xray_update_runtime, "_asset_filename", lambda: "Xray-linux-64.zip")
    monkeypatch.setattr(
        xray_update_runtime,
        "_find_asset",
        lambda release, name: {"name": name, "browser_download_url": "https://example.invalid/xray.zip"},
    )
    monkeypatch.setattr(xray_update_runtime, "_download", lambda url, path: path.write_bytes(b"archive"))
    monkeypatch.setattr(xray_update_runtime, "_expected_digest", lambda *args: "digest")
    monkeypatch.setattr(xray_update_runtime, "_sha256", lambda path: "digest")
    monkeypatch.setattr(
        xray_update_runtime,
        "_extract_binary",
        lambda archive, destination: destination.write_text("new-binary", encoding="utf-8"),
    )

    version_calls = {"live": 0}

    def installed_version(path=None):
        if path is not None and Path(path) != binary:
            return "26.9.9"
        version_calls["live"] += 1
        return "26.7.28" if version_calls["live"] == 1 else "26.9.9"

    monkeypatch.setattr(xray_update_runtime, "_installed_version", installed_version)
    monkeypatch.setattr(
        xray_update_runtime,
        "_regenerate_xray_config",
        lambda: config.write_text("new-config", encoding="utf-8"),
        raising=False,
    )

    tested = []

    def test_config(path):
        tested.append((Path(path), config.read_text(encoding="utf-8")))
        if config.read_text(encoding="utf-8") == "old-config":
            raise xray_update_runtime.XrayUpdateRuntimeError("new Xray rejected old config")

    monkeypatch.setattr(xray_update_runtime, "_test_config", test_config)
    monkeypatch.setattr(
        xray_update_runtime,
        "_run",
        lambda *args, **kwargs: subprocess.CompletedProcess(args=args[0], returncode=0, stdout="", stderr=""),
    )
    monkeypatch.setattr(xray_update_runtime, "_write_result", lambda payload: None)
    monkeypatch.setattr(xray_update_runtime, "log_operation", lambda *args, **kwargs: None)

    result = xray_update_runtime.update_xray("prerelease")

    assert result["ok"] is True
    assert config.read_text(encoding="utf-8") == "new-config"
    assert tested
    assert all(body == "new-config" for _path, body in tested)
