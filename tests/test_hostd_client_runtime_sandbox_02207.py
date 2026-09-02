from pathlib import Path


ROOT = Path(__file__).parents[1]
UNIT = ROOT / "hostd" / "systemd" / "sg-hostd.service"


def _read_write_paths() -> set[str]:
    source = UNIT.read_text(encoding="utf-8")
    line = next(
        value
        for value in source.splitlines()
        if value.startswith("ReadWritePaths=")
    )
    return set(line.partition("=")[2].split())


def test_hostd_sandbox_allows_managed_client_runtime_writes_without_opening_etc():
    source = UNIT.read_text(encoding="utf-8")
    paths = _read_write_paths()

    assert "ProtectSystem=strict" in source
    assert "/etc" not in paths
    assert "-/usr/local/etc/xray" in paths
    assert "-/etc/amnezia/amneziawg" in paths
    assert "-/etc/sysctl.d" in paths
    assert "-/etc/mihomo" in paths
    assert "-/etc/sing-box" in paths
    assert "-/var/lib/sg-gateway" in paths
