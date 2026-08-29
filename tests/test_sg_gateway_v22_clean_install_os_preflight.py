from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INSTALLER = ROOT / "deploy" / "install-from-github.sh"


def _installer_source() -> str:
    return INSTALLER.read_text(encoding="utf-8")


def test_clean_install_waits_for_cloud_init_before_disk_and_apt_work() -> None:
    source = _installer_source()

    assert "cloud-init status --wait" in source
    assert source.index("wait_for_cloud_init") < source.index(
        'require_free_space /tmp "temporary storage"'
    )


def test_clean_install_updates_ubuntu_before_downloading_gateway_source() -> None:
    source = _installer_source()

    assert "full-upgrade -y" in source
    assert "autoremove -y" in source
    assert source.index("prepare_clean_ubuntu") < source.index(
        "Downloading GitHub branch"
    )


def test_reboot_required_stops_before_gateway_install_without_rebooting() -> None:
    source = _installer_source()

    assert "/var/run/reboot-required" in source
    assert "repeat the same SG-Gateway install command" in source
    assert "systemctl reboot" not in source
    assert "shutdown -r" not in source
