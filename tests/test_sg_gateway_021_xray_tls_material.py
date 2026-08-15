from __future__ import annotations

import stat
from pathlib import Path

from hostd.sg_hostd import client_runtime


def test_xray_tls_material_is_copied_for_service_group(monkeypatch, tmp_path):
    live_root = tmp_path / "letsencrypt-live"
    source_dir = live_root / "panel.example.com"
    source_dir.mkdir(parents=True)
    (source_dir / "fullchain.pem").write_bytes(b"CERTIFICATE\n")
    (source_dir / "privkey.pem").write_bytes(b"PRIVATE KEY\n")

    tls_dir = tmp_path / "xray-tls"
    cert = tls_dir / "fullchain.pem"
    key = tls_dir / "privkey.pem"
    monkeypatch.setattr(client_runtime, "LETSENCRYPT_LIVE_ROOT", live_root)
    monkeypatch.setattr(client_runtime, "XRAY_TLS_DIR", tls_dir)
    monkeypatch.setattr(client_runtime, "XRAY_TLS_CERT", cert)
    monkeypatch.setattr(client_runtime, "XRAY_TLS_KEY", key)
    monkeypatch.setattr(client_runtime, "_xray_service_group_gid", lambda: 1234)

    ownership: list[tuple[Path, int, int]] = []
    monkeypatch.setattr(
        client_runtime.os,
        "chown",
        lambda path, uid, gid: ownership.append((Path(path), uid, gid)),
    )

    copied_cert, copied_key = client_runtime._sync_xray_tls_material(
        "panel.example.com"
    )

    assert copied_cert == str(cert)
    assert copied_key == str(key)
    assert cert.read_bytes() == b"CERTIFICATE\n"
    assert key.read_bytes() == b"PRIVATE KEY\n"
    assert stat.S_IMODE(tls_dir.stat().st_mode) == 0o777
    assert stat.S_IMODE(cert.stat().st_mode) == 0o777
    assert stat.S_IMODE(key.stat().st_mode) == 0o777
    assert ownership[-2][1:] == (0, 1234)
    assert ownership[-1][1:] == (0, 1234)


def test_xray_config_uses_private_runtime_tls_copy():
    source = Path("hostd/sg_hostd/client_runtime.py").read_text(encoding="utf-8")
    assert 'cert, key = _sync_xray_tls_material(domain)' in source
    tls_block = source.split("tls_needed =", 1)[1].split("if \"xhttp_tls\"", 1)[0]
    assert "/etc/letsencrypt/live/" not in tls_block
    assert 'XRAY_TLS_DIR = Path("/usr/local/etc/xray/tls")' in source


def test_certificate_refresh_reapplies_client_runtimes():
    source = Path("deploy/configure-panel-access.sh").read_text(encoding="utf-8")
    renew = source.split("renew_https(){", 1)[1].split("\nrefresh_https(){", 1)[0]
    refresh = source.split("refresh_https(){", 1)[1].split("\nrollback_https(){", 1)[0]
    assert "apply_client_runtime" in renew
    assert "apply_client_runtime" in refresh
