from pathlib import Path

from app.maintenance import core_updates
from hostd.sg_hostd import core_update_runtime


ROOT = Path(__file__).resolve().parents[1]


def test_core_update_uses_real_installer_runtime_env():
    assert core_updates.INSTALL_ENV.name == "runtime.env"
    assert core_update_runtime.INSTALL_ENV.name == "runtime.env"


def test_full_uninstaller_is_explicit_and_cleans_managed_runtime():
    text = (ROOT / "deploy/full-uninstall-ubuntu.sh").read_text(encoding="utf-8")
    assert "DELETE SG-GATEWAY" in text
    for marker in (
        "/opt/sg-gateway",
        "/etc/sg-gateway",
        "/var/lib/sg-gateway",
        "/root/sg-gateway-backups",
        "/usr/local/bin/xray",
        "/usr/local/bin/mihomo",
        "/usr/local/bin/sing-box",
        "/usr/local/bin/wgcf-cli",
        "/var/lib/dkms/amneziawg/1.0.0",
        "certbot delete --cert-name",
    ):
        assert marker in text


def test_full_uninstaller_removes_all_ports_opened_by_installer():
    text = (ROOT / "deploy/full-uninstall-ubuntu.sh").read_text(encoding="utf-8")
    for marker in (
        '"80/tcp"',
        '"${XRAY_PORT}/tcp"',
        '"${XHTTP_REALITY_PORT}/tcp"',
        '"${XHTTP_TLS_PORT}/tcp"',
        '"${AWG_PORT}/udp"',
        '"${HYSTERIA2_PORT}/udp"',
        '"${MIHOMO_PORT}/tcp"',
        '"${ANYTLS_PORT}/tcp"',
        '"${TUIC_PORT}/udp"',
    ):
        assert marker in text
