from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_installer_uses_five_vendored_engines():
    installer = read("install.sh")
    stage_start = installer.index("stage_engine_runtimes() {")
    stage_end = installer.index("\n}\n", stage_start)
    stage = installer[stage_start:stage_end]

    assert "[Engine 1/5] AmneziaWG" in stage
    assert "[Engine 2/5] Xray" in stage
    assert "[Engine 3/5] Mihomo" in stage
    assert "[Engine 4/5] sing-box" in stage
    assert "[Engine 5/5] WARP" in stage
    assert "install_amneziawg_from_vendor" in stage
    assert "install_xray_from_vendor" in stage
    assert "install_mihomo_from_vendor" in stage
    assert "install_sing_box_from_vendor" in stage
    assert "install_wgcf_from_vendor" in stage


def test_all_six_vendor_files_are_required():
    installer = read("install.sh")
    for name in (
        "Xray-linux-64.zip",
        "mihomo-linux-amd64-v1.19.29.gz",
        "sing-box-1.13.14-linux-amd64.tar.gz",
        "wgcf-cli-linux-64.tar.zstd",
        "amneziawg-tools-1.0.20260618-2.tar.gz",
        "amneziawg-linux-kernel-module-1.0.20260329-2.tar.gz",
    ):
        assert name in installer
        assert (ROOT / "vendor" / "cores" / name).is_file()


def test_dkms_reinstall_cleans_only_pinned_stale_state():
    installer = read("install.sh")
    assert 'dkms remove -m amneziawg -v "$AMNEZIAWG_DKMS_VERSION" --all' in installer
    assert 'rm -rf "/var/lib/dkms/amneziawg/${AMNEZIAWG_DKMS_VERSION}"' in installer
    assert 'rm -rf "/usr/src/amneziawg-${AMNEZIAWG_DKMS_VERSION}"' in installer
    assert 'dkms add -m amneziawg -v "$AMNEZIAWG_DKMS_VERSION"' in installer
    assert 'dkms build -m amneziawg -v "$AMNEZIAWG_DKMS_VERSION"' in installer
    assert 'dkms install -m amneziawg -v "$AMNEZIAWG_DKMS_VERSION"' in installer


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
