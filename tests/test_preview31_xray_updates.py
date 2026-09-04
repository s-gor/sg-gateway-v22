from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HOSTD = ROOT / "hostd"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(HOSTD) not in sys.path:
    sys.path.insert(0, str(HOSTD))

from app.maintenance import xray_updates
from app.xray import profiles
from sg_hostd import client_runtime
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
    assert profiles._version_supported("26.7.28") is True
    assert profiles._version_supported("26.8.1") is True
    assert profiles._version_supported("26.7.11") is False
    assert profiles._version_supported("26.6.27") is False


def test_hostd_minimum_policy_accepts_newer(monkeypatch):
    monkeypatch.setattr(
        client_runtime,
        "_run",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            args=["xray", "version"], returncode=0, stdout="Xray 26.7.28 test\n", stderr=""
        ),
    )
    assert client_runtime._require_xray_version() == "26.7.28"


def test_update_commands_are_explicitly_allowlisted():
    commands = list_allowed_commands()
    assert "xray.update.stable.start" in commands
    assert "xray.update.prerelease.start" in commands


def test_installer_bootstraps_26627_but_preserves_supported_newer():
    installer = (ROOT / "install.sh").read_text(encoding="utf-8")
    assert 'XRAY_REQUIRED_VERSION="v26.7.28"' in installer
    assert 'XRAY_MINIMUM_VERSION="v26.7.28"' in installer
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
    assert manifest["xray"]["minimum_version"] == "v26.7.28"
    assert manifest["xray"]["required_version"] == "v26.7.28"
    assert manifest["xray"]["updates"]["automatic_rollback"] is True
    assert "Backups" in template and "Updates" in template
    assert "Стабильная версия" in template
    assert "Предварительная версия" in template
    assert "Понижение запрещено" in template
    assert "SHA-256" in template
    assert "_restore_binary" in runtime
    assert '"systemctl", "restart", "xray.service"' in runtime
