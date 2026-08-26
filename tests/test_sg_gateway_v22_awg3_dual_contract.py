from __future__ import annotations

import json
import re
from pathlib import Path

from app.clients import repository
from app.clients.exports import build_awg3_config
from app.connections.settings import get_connection_settings, update_connection_settings
from app.db import connect, init_db


def test_awg2_and_awg3_are_independent_device_credentials(tmp_path, monkeypatch):
    monkeypatch.setenv("SG_GATEWAY_DATA_DIR", str(tmp_path))
    monkeypatch.setattr("app.engines.provisioning._awg_keypair", lambda: ("awg2-private", "awg2-public"))
    monkeypatch.setattr("app.engines.provisioning._awg3_keypair", lambda: ("awg3-private", "awg3-public"))
    init_db()
    assert update_connection_settings("amneziawg", "198.51.100.10", 9999, get_connection_settings("amneziawg").config)
    assert update_connection_settings("amneziawg3", "198.51.100.10", 9999, get_connection_settings("amneziawg3").config)
    assert get_connection_settings("amneziawg").port == 585
    assert get_connection_settings("amneziawg3").port == 586

    client_id = repository.create_client("Dual AWG", "amneziawg,amneziawg3,amneziawg31")
    assert client_id
    device = repository.get_primary_device(client_id)
    assert device is not None
    creds = {item.engine: json.loads(item.config_json or "{}") for item in repository.list_device_credentials(device.id)}
    assert set(creds) == {"amneziawg", "amneziawg3", "amneziawg31"}
    assert creds["amneziawg"]["address"].startswith("10.66.")
    assert creds["amneziawg3"]["address"].startswith("10.67.")
    assert creds["amneziawg"]["private_key"] != creds["amneziawg3"]["private_key"]


def test_awg3_export_has_generation3_fields(tmp_path, monkeypatch):
    monkeypatch.setenv("SG_GATEWAY_DATA_DIR", str(tmp_path))
    monkeypatch.setattr("app.engines.provisioning._awg3_keypair", lambda: ("private-3", "public-3"))
    init_db()
    settings = get_connection_settings("amneziawg3")
    cfg = dict(settings.config)
    cfg["server_public_key"] = "server-3"
    assert update_connection_settings("amneziawg3", "203.0.113.8", 586, cfg)
    client_id = repository.create_client("Only AWG3", "amneziawg3")
    assert client_id
    client = repository.get_client(client_id)
    device = repository.get_primary_device(client_id)
    assert client and device
    with connect() as connection:
        payload = json.loads(connection.execute("SELECT config_json FROM device_credentials WHERE device_id=? AND engine='amneziawg3'", (device.id,)).fetchone()[0])
        payload.update({"jc":4,"jmin":10,"jmax":50,"s1":64,"s2":96,"s3":48,"s4":12,"h1":"101","h2":"102","h3":"103","h4":"104","header_protection_key":"header-key","content_padding_addition":"10-100","rekey_after_time":"100-120","rekey_timeout":"3-7","reject_after_time":"150-180","keepalive_timeout":"5-15","max_handshake_attempts":"15-20","server_public_key":"server-3"})
        connection.execute("UPDATE device_credentials SET status='applied', config_json=? WHERE device_id=? AND engine='amneziawg3'", (json.dumps(payload), device.id))
    body = build_awg3_config(client, device).body
    for marker in ("S3 = 48", "S4 = 12", "HeaderProtectionKey = header-key", "ContentPaddingAddition = 10-100", "Endpoint = 203.0.113.8:586"):
        assert marker in body


def test_awg3_installer_is_userspace_only_and_awg2_stays_frozen():
    text = Path("deploy/install-core.sh").read_text(encoding="utf-8")
    assert 'AMNEZIAWG_TOOLS_VERSION="1.0.20260618-2"' in text
    assert 'AMNEZIAWG_KMOD_VERSION="1.0.20260329-2"' in text
    assert 'AWG3_TOOLS_VERSION="3.1.20260812"' in text
    assert 'PREFIX="$PREFIX/awg3" install' in text
    assert 'amneziawg-go-linux-amd64-v3.1.20260814' in text
    assert 'amneziawg-linux-kernel-module-3.0' not in text
    assert 'AMNEZIAWG_KMOD_VERSION="3.' not in text


def test_awg3_runtime_does_not_auto_clone_awg2_credentials():
    text = Path("hostd/sg_hostd/awg3_runtime.py").read_text(encoding="utf-8")
    assert "_ensure_credentials" not in text
    assert 'ENGINE = "amneziawg3"' in text
    assert 'cr.get_connection_settings("amneziawg3")' in text
    assert 'AWG3_ROOT / "bin/awg"' in text
    assert "modprobe" not in text
    assert "dkms" not in text.lower()


def test_dual_awg_ui_is_scoped_and_keeps_button_palette():
    html = Path("app/web/templates/connections.html").read_text(encoding="utf-8")
    css = Path("app/web/static/sg-awg-dual-v1.css").read_text(encoding="utf-8")
    assert "AWG2" in html and "AWG3" in html
    assert "update_amneziawg3" in html
    assert 'class="button primary"' in html
    assert not re.search(r"(?m)^\s*\.button\b", css)
    assert ".page-connections .awgd-" in css


def test_client_dataclass_keeps_pre_awg3_constructor_compatible():
    client = repository.Client(1, "Legacy", True, None, "applied", "applied")
    assert client.xray_status == "applied"
    assert client.awg3_status == "missing"


def test_device_picker_orders_both_awg_generations():
    body = Path("app/web/static/sg-device-collapse-v1.js").read_text(encoding="utf-8")
    assert "'amneziawg3'" in body
    assert "'amneziawg31'" in body
    assert "AmneziaWG 3.0" in body
    assert "AmneziaWG 3.1" in body
    assert "UDP 586 · userspace-конфигурация и QR" in body
