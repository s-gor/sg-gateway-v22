from __future__ import annotations

from pathlib import Path

from app.clients import repository
from app.connections.settings import get_connection_settings, update_connection_settings
from app.db import init_db


def test_awg2_awg3_settings_remain_migration_compatible_but_client_access_is_retired(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setenv("SG_GATEWAY_DATA_DIR", str(tmp_path))
    init_db()

    assert update_connection_settings(
        "amneziawg",
        "198.51.100.10",
        9999,
        get_connection_settings("amneziawg").config,
    )
    assert update_connection_settings(
        "amneziawg3",
        "198.51.100.10",
        9999,
        get_connection_settings("amneziawg3").config,
    )
    assert get_connection_settings("amneziawg").port == 585
    assert get_connection_settings("amneziawg3").port == 586

    client_id = repository.create_client(
        "Current AWG",
        "amneziawg,amneziawg3,amneziawg31",
    )
    assert client_id
    device = repository.get_primary_device(client_id)
    assert device is not None
    assert {item.engine for item in repository.list_device_credentials(device.id)} == {
        "amneziawg31"
    }


def test_awg3_only_new_client_request_is_rejected(tmp_path, monkeypatch):
    monkeypatch.setenv("SG_GATEWAY_DATA_DIR", str(tmp_path))
    init_db()

    assert repository.create_client("Only retired AWG3", "amneziawg3") is None


def test_awg3_installer_media_remains_pinned_for_migration_compatibility():
    text = Path("deploy/install-core.sh").read_text(encoding="utf-8")
    assert 'AMNEZIAWG_TOOLS_VERSION="1.0.20260618-2"' in text
    assert 'AWG3_TOOLS_VERSION="3.0.20260805"' in text
    assert 'amneziawg-go-linux-amd64-v3.0.0' in text
    assert 'amneziawg-linux-kernel-module-3.0' not in text


def test_awg3_runtime_compatibility_code_does_not_clone_awg2_credentials():
    text = Path("hostd/sg_hostd/awg3_runtime.py").read_text(encoding="utf-8")
    assert "_ensure_credentials" not in text
    assert 'ENGINE = "amneziawg3"' in text
    assert 'cr.get_connection_settings("amneziawg3")' in text
    assert 'AWG3_ROOT / "bin/awg"' in text
    assert "modprobe" not in text
    assert "dkms" not in text.lower()


def test_client_dataclass_keeps_pre_awg3_constructor_compatible():
    client = repository.Client(1, "Legacy", True, None, "applied", "applied")
    assert client.xray_status == "applied"
    assert client.awg3_status == "missing"
