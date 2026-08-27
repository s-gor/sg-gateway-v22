from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_installer_uses_six_vendored_engine_steps_with_isolated_awg3():
    installer = read("install.sh")
    stage_start = installer.index("stage_engine_runtimes() {")
    stage_end = installer.index("\n}\n", stage_start)
    stage = installer[stage_start:stage_end]

    assert "[Engine 1/6] AmneziaWG 2" in stage
    assert "[Engine 2/6] AmneziaWG 3 userspace" in stage
    assert "[Engine 3/6] Xray" in stage
    assert "[Engine 4/6] Mihomo" in stage
    assert "[Engine 5/6] sing-box" in stage
    assert "install_amneziawg_from_vendor" in stage
    assert "install_amneziawg3_userspace_from_vendor" in stage
    assert "[Engine 6/6] WARP" in stage
    assert "install_xray_from_vendor" in stage
    assert "install_mihomo_from_vendor" in stage
    assert "install_sing_box_from_vendor" in stage
    assert "install_wgcf_from_vendor" in stage


def test_all_eight_vendor_files_are_required():
    installer = read("install.sh")
    for name in (
        "Xray-linux-64.zip",
        "mihomo-linux-amd64-v1.19.29.gz",
        "sing-box-1.13.14-linux-amd64.tar.gz",
        "wgcf-cli-linux-64.tar.zstd",
        "amneziawg-tools-1.0.20260618-2.tar.gz",
        "amneziawg-linux-kernel-module-1.0.20260329-2.tar.gz",
        "amneziawg-tools-3.0.20260805.tar.gz",
        "amneziawg-go-linux-amd64-v3.0.0",
    ):
        assert name in installer
        assert (ROOT / "vendor" / "cores" / name).is_file()


def test_dkms_reinstall_cleans_stale_module_and_forces_frozen_awg2():
    installer = read("install.sh")
    assert 'ip link delete awg0' in installer
    assert 'ip link delete awg3' in installer
    assert 'modprobe -r amneziawg' in installer
    assert "grep -q '^amneziawg ' /proc/modules" in installer
    assert 'dkms remove -m amneziawg -v "$AMNEZIAWG_DKMS_VERSION" --all' in installer
    assert 'rm -rf "/var/lib/dkms/amneziawg/${AMNEZIAWG_DKMS_VERSION}"' in installer
    assert 'rm -rf "/usr/src/amneziawg-${AMNEZIAWG_DKMS_VERSION}"' in installer
    assert 'find "/lib/modules/$(uname -r)" -type f' in installer
    assert "-path '*/updates/dkms/*' -delete" in installer
    assert 'dkms install -m amneziawg -v "$AMNEZIAWG_DKMS_VERSION" --force' in installer
    assert 'modinfo -F version amneziawg' in installer
    assert '/sys/module/amneziawg/version' in installer
    assert '[[ "$module_version" =~ ^1\. ]]' in installer


def test_update_preserves_only_real_awg2_runtime():
    installer = read("install.sh")
    ready = installer[installer.index("amneziawg_runtime_ready() {"):installer.index("install_amneziawg_from_vendor() {")]
    assert 'tools_version="$(awg --version' in ready
    assert 'module_version="$(modinfo -F version amneziawg' in ready
    assert '/sys/module/amneziawg/version' in ready
    assert '[[ "$tools_version" == *"v1."* ]]' in ready
    assert '[[ "$module_version" =~ ^1\. ]]' in ready


def test_full_uninstall_removes_orphaned_awg_dkms_module_files():
    uninstall = read("deploy/full-uninstall-ubuntu.sh")
    assert 'dkms remove -m amneziawg -v 1.0.0 --all' in uninstall
    assert 'find /lib/modules -type f' in uninstall
    assert "-path '*/updates/dkms/*' -delete" in uninstall
    assert uninstall.index('find /lib/modules -type f') < uninstall.index('depmod -a')


def test_stage7_accepts_runtime_conflict_without_hiding_route_failures():
    installer = read("install.sh")
    assert "create_client('Smoke client', 'mihomo,sgclient')" in installer
    assert "detail = client.get(detail_path)" in installer
    assert "assert detail.status_code == 200" in installer
    assert "response.status_code in (200, 409)" in installer
    assert "empty HTTP 200 response" in installer


def test_https_helper_is_executable_in_installed_tree():
    installer = read("install.sh")
    assert 'chmod 0755 "$PREFIX/deploy/configure-panel-access.sh"' in installer


def test_awg3_vendor_set_has_no_3x_kernel_module():
    installer = read("install.sh")
    assert "amneziawg-linux-kernel-module-3.0" not in installer
    assert not any((ROOT / "vendor" / "cores").glob("amneziawg-linux-kernel-module-3.0*"))
