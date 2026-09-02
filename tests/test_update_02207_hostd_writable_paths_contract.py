from pathlib import Path


ROOT = Path(__file__).parents[1]
UNIT = ROOT / "hostd" / "systemd" / "sg-hostd.service"
UPDATER = ROOT / "deploy" / "update-from-github-02207.sh"
OLD_WRITABLE_PATHS = (
    "ReadWritePaths=-/run/sg-gateway -/usr/local/share/xray "
    "-/etc/sg-gateway/naiveproxy -/var/lib/sg-gateway"
)


def test_updater_preflight_and_staging_use_the_exact_hostd_writable_paths_contract():
    unit = UNIT.read_text(encoding="utf-8")
    updater = UPDATER.read_text(encoding="utf-8")
    writable_paths = next(
        line
        for line in unit.splitlines()
        if line.startswith("ReadWritePaths=")
    )

    assert updater.count(writable_paths) == 2
    assert OLD_WRITABLE_PATHS not in updater
