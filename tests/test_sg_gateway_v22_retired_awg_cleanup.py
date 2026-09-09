from __future__ import annotations

from pathlib import Path


def test_retirement_targets_only_awg2_and_awg3(monkeypatch, tmp_path: Path):
    from app.maintenance import retire_legacy_awg as retirement

    unit_awg2 = tmp_path / "sg-gateway-awg.service"
    unit_awg3 = tmp_path / "sg-gateway-awg3.service"
    unit_awg31 = tmp_path / "sg-gateway-awg31.service"
    cfg_awg2 = tmp_path / "awg0.conf"
    cfg_awg3 = tmp_path / "awg3.conf"
    cfg_awg31 = tmp_path / "awg31.conf"

    for path in (unit_awg2, unit_awg3, unit_awg31, cfg_awg2, cfg_awg3, cfg_awg31):
        path.write_text("keep-or-retire", encoding="utf-8")

    monkeypatch.setattr(
        retirement,
        "LEGACY_PATHS",
        (unit_awg2, unit_awg3, cfg_awg2, cfg_awg3),
    )

    commands: list[tuple[str, ...]] = []

    def fake_run(command):
        commands.append(tuple(command))
        return 0

    result = retirement.retire_legacy_awg(run=fake_run)

    assert result["retired_engines"] == ["amneziawg", "amneziawg3"]
    assert not unit_awg2.exists()
    assert not unit_awg3.exists()
    assert not cfg_awg2.exists()
    assert not cfg_awg3.exists()
    assert unit_awg31.exists()
    assert cfg_awg31.exists()
    assert all("awg31" not in " ".join(command).lower() for command in commands)
    assert ("systemctl", "stop", "sg-gateway-awg.service") in commands
    assert ("systemctl", "stop", "sg-gateway-awg3.service") in commands
    assert ("systemctl", "disable", "sg-gateway-awg.service") in commands
    assert ("systemctl", "disable", "sg-gateway-awg3.service") in commands
    assert ("ip", "link", "delete", "dev", "awg0") in commands
    assert ("ip", "link", "delete", "dev", "awg3") in commands


def test_retirement_is_idempotent(monkeypatch, tmp_path: Path):
    from app.maintenance import retire_legacy_awg as retirement

    missing_paths = (
        tmp_path / "sg-gateway-awg.service",
        tmp_path / "sg-gateway-awg3.service",
        tmp_path / "awg0.conf",
        tmp_path / "awg3.conf",
    )
    monkeypatch.setattr(retirement, "LEGACY_PATHS", missing_paths)

    commands: list[tuple[str, ...]] = []

    def fake_run(command):
        commands.append(tuple(command))
        return 0

    first = retirement.retire_legacy_awg(run=fake_run)
    second = retirement.retire_legacy_awg(run=fake_run)

    assert first["retired_engines"] == second["retired_engines"]
    assert all(not path.exists() for path in missing_paths)


def test_historical_awg3_bootstrap_entrypoint_retires_instead_of_recreating(monkeypatch):
    from app.maintenance import awg3_idle_bootstrap as bootstrap

    expected = {
        "changed": True,
        "message": "retired AWG2/AWG3 runtime state removed",
        "retired_engines": ["amneziawg", "amneziawg3"],
    }
    monkeypatch.setattr(bootstrap, "retire_legacy_awg", lambda: expected)

    assert bootstrap.bootstrap_idle_awg3() == expected
