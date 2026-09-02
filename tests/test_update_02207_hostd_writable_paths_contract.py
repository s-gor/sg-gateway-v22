from pathlib import Path


ROOT = Path(__file__).parents[1]
UNIT = ROOT / "hostd" / "systemd" / "sg-hostd.service"
UPDATER = ROOT / "deploy" / "update-from-github-02207.sh"


def test_updater_preflight_accepts_the_exact_hostd_writable_paths_contract():
    unit = UNIT.read_text(encoding="utf-8")
    updater = UPDATER.read_text(encoding="utf-8")
    writable_paths = next(
        line
        for line in unit.splitlines()
        if line.startswith("ReadWritePaths=")
    )

    assert writable_paths in updater
