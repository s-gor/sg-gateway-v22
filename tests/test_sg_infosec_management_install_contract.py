from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_bridge_unit_is_unprivileged_and_unix_socket_only():
    unit = read("deploy/systemd/sg-infosec-management-bridge.service")
    assert "User=sg-infosec-bridge" in unit
    assert "Group=sg-infosec-bridge" in unit
    assert "SupplementaryGroups=sg-infosec sg-gateway" in unit
    assert "PartOf=sg-gateway.service" in unit
    assert "AF_INET" not in unit
    assert "ListenStream=" not in unit
    assert "585" not in unit and "586" not in unit and "587" not in unit


def test_installer_creates_narrow_admin_source_and_links_unit():
    script = read("deploy/install-sg-infosec-management-bridge.sh")
    assert "useradd --system" in script
    assert "source_id: sg-gateway-management" in script
    assert "user: sg-infosec-bridge" in script
    assert "- read_admin" in script
    assert "- write_admin" in script
    assert "systemctl link" in script
    assert "systemctl enable" not in script
    assert "control.sock" in script
    assert "585" not in script and "586" not in script and "587" not in script


def test_panel_unit_runs_fixed_installer_without_giving_web_root():
    unit = read("deploy/systemd/sg-gateway.service")
    assert "User=sg-gateway" in unit
    assert "NoNewPrivileges=true" in unit
    assert "ExecStartPre=-+/opt/sg-gateway/deploy/install-sg-infosec-management-bridge.sh" in unit
    assert "Wants=network-online.target sg-hostd.service sg-infosec-management-bridge.service" in unit
