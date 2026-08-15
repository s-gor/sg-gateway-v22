from pathlib import Path
import json
import sqlite3
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def test_repository_is_clean_021_baseline() -> None:
    version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    manifest = json.loads((ROOT / "release-manifest.json").read_text(encoding="utf-8"))
    assert version.startswith("0.1.0-021.")
    assert manifest["version"] == version
    assert manifest["runtime"] == "native-systemd"


def test_clean_seed_uses_awg_udp_585() -> None:
    with sqlite3.connect(ROOT / "data/sg-gateway.sqlite") as connection:
        row = connection.execute(
            "SELECT port FROM connection_settings WHERE engine='amneziawg'"
        ).fetchone()
    assert row and int(row[0]) == 585


def test_runtime_invariants_remain_in_source() -> None:
    installer = (ROOT / "install.sh").read_text(encoding="utf-8")
    constants = (ROOT / "app/constants.py").read_text(encoding="utf-8")
    connections = (ROOT / "app/web/templates/connections.html").read_text(
        encoding="utf-8"
    )
    assert 'DEFAULT_AWG_PORT="585"' in installer
    assert "AMNEZIAWG_UDP_PORT = 585" in constants
    assert 'min="585" max="585"' in connections
    assert "stage9_ensure_warp" in installer
    assert "Salamander" in connections


def test_obsolete_repository_debris_is_absent() -> None:
    forbidden = [
        "install.sh.pre-v51",
        "README-SG-GATEWAY-015.md",
        "README-SG-GATEWAY-020.md",
        "SG-PANEL-HYSTERIA2-SALAMANDER-INSTRUCTIONS.txt",
        "scripts/docker-dev.ps1",
        "scripts/docker-prod.ps1",
        "docs/docker.md",
        "deploy/update.sh",
        "deploy/uninstall.sh",
        "deploy/rollback.sh",
    ]
    assert not [name for name in forbidden if (ROOT / name).exists()]


def test_shell_entry_points_parse() -> None:
    for path in (ROOT / "install.sh", ROOT / "build-run.sh"):
        subprocess.run(["bash", "-n", str(path)], check=True)
