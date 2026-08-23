from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_dev_clean_install_handles_awg2_module_load_rejection():
    wrapper = read("deploy/install-from-github.sh")
    installer = read("install.sh")

    # Keep the source installer contract exact: the GitHub wrapper must fail
    # closed if the native installer changes instead of patching an arbitrary
    # command sequence.
    target = '''  dkms install -m amneziawg -v "$AMNEZIAWG_DKMS_VERSION" --force\n  modprobe amneziawg\n  modinfo amneziawg\n'''
    assert installer.count(target) == 1

    assert "enable_awg2_userspace_fallback()" in wrapper
    assert "AWG2 fallback patch contract mismatch" in wrapper
    assert 'if modprobe amneziawg; then' in wrapper
    assert "kernel module unavailable; userspace fallback will be used" in wrapper
    assert 'enable_awg2_userspace_fallback "$SOURCE_DIR/install.sh"' in wrapper
    assert "AWG2 runtime: kernel-first with vendored userspace fallback" in wrapper


def test_awg2_service_uses_vendored_userspace_only_as_fallback():
    service = read("deploy/sg-gateway-awg.service")
    installer = read("install.sh")

    assert "Environment=WG_QUICK_USERSPACE_IMPLEMENTATION=/opt/sg-gateway/awg3/bin/amneziawg-go" in service
    assert 'AWG3_GO_VENDOR_FILE="amneziawg-go-linux-amd64-v3.0.0"' in installer
    assert 'install -m 0755 "$go_src" "$PREFIX/bin/amneziawg-go"' in installer

    # The frozen AWG2 kernel module remains installed and preferred.  This fix
    # adds a fallback; it does not replace AWG2 with the AWG3 service/runtime.
    assert 'AMNEZIAWG_KMOD_VERSION="1.0.20260329-2"' in installer
    assert 'dkms install -m amneziawg -v "$AMNEZIAWG_DKMS_VERSION" --force' in installer
