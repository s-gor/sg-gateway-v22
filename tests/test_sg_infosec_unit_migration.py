from pathlib import Path
import stat

import pytest

from app.security.sg_infosec_unit_migration import migrate_unit


OLD_UNIT = """[Unit]
Description=SG-Gateway panel
After=network-online.target sg-hostd.service
Wants=network-online.target sg-hostd.service

[Service]
Type=simple
User=sg-gateway
EnvironmentFile=/etc/sg-gateway/sg-gateway.env
Environment=SG_INFOSEC_GUARD_SETTINGS=/etc/sg-gateway/old-guard.json
ExecStart=/opt/sg-gateway/.venv/bin/waitress-serve --host=0.0.0.0 --port=18080 app.production:app
Restart=on-failure

[Install]
WantedBy=multi-user.target
"""


def test_migration_preserves_runtime_command_and_adds_complete_integration(tmp_path: Path):
    unit = tmp_path / "sg-gateway.service"
    unit.write_text(OLD_UNIT, encoding="utf-8")
    unit.chmod(0o640)

    assert migrate_unit(unit) is True
    body = unit.read_text(encoding="utf-8")

    assert "After=network-online.target sg-hostd.service sg-infosec-management-bridge.service" in body
    assert "Wants=network-online.target sg-hostd.service sg-infosec-management-bridge.service" in body
    assert body.count("Environment=SG_INFOSEC_GUARD_SETTINGS=") == 1
    assert "Environment=SG_INFOSEC_GUARD_SETTINGS=/var/lib/sg-gateway/infosec/guard.json" in body
    assert "Environment=SG_INFOSEC_REPUTATION_FILE=/var/lib/sg-gateway/infosec/reputation.json" in body
    assert "Environment=SG_INFOSEC_ALERTS_FILE=/var/lib/sg-gateway/infosec/alerts.jsonl" in body
    assert body.count("ExecStartPre=-+/opt/sg-gateway/deploy/install-sg-infosec-management-bridge.sh") == 1
    assert "--port=18080 app.production:app" in body
    assert stat.S_IMODE(unit.stat().st_mode) == 0o640


def test_migration_is_idempotent(tmp_path: Path):
    unit = tmp_path / "sg-gateway.service"
    unit.write_text(OLD_UNIT, encoding="utf-8")

    assert migrate_unit(unit) is True
    first = unit.read_bytes()
    assert migrate_unit(unit) is False
    assert unit.read_bytes() == first


def test_migration_adds_missing_dependency_directives(tmp_path: Path):
    unit = tmp_path / "sg-gateway.service"
    unit.write_text(
        "[Unit]\nDescription=panel\n\n[Service]\nExecStart=/bin/true\n",
        encoding="utf-8",
    )

    migrate_unit(unit)
    body = unit.read_text(encoding="utf-8")
    assert "After=sg-infosec-management-bridge.service" in body
    assert "Wants=sg-infosec-management-bridge.service" in body


def test_migration_rejects_malformed_unit_without_exec_start(tmp_path: Path):
    unit = tmp_path / "sg-gateway.service"
    unit.write_text("[Unit]\nDescription=panel\n[Service]\nType=simple\n", encoding="utf-8")

    with pytest.raises(ValueError, match="ExecStart"):
        migrate_unit(unit)
