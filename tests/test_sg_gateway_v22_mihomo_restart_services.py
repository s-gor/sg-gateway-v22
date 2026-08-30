from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType


ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "app/mihomo/restart_services.py"
RUNTIME = ROOT / "hostd/sg_hostd/mihomo_runtime.py"


def _load_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("restart_services", MODULE)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_restart_restarts_both_applied_services(monkeypatch, tmp_path: Path) -> None:
    module = _load_module()
    mihomo_config = tmp_path / "mihomo.yaml"
    singbox_config = tmp_path / "singbox.json"
    mihomo_config.write_text("mixed-port: 7890\n", encoding="utf-8")
    singbox_config.write_text("{}\n", encoding="utf-8")
    monkeypatch.setattr(
        module,
        "SERVICES",
        (
            (mihomo_config, "mihomo.service"),
            (singbox_config, "sg-gateway-singbox.service"),
        ),
    )
    calls: list[list[str]] = []
    monkeypatch.setattr(module, "_run", lambda command: calls.append(command))

    payload = module.restart_applied_services()

    assert payload == {
        "ok": True,
        "message": "Сервисы перезапущены",
        "services": ["mihomo.service", "sg-gateway-singbox.service"],
    }
    assert calls == [
        ["systemctl", "restart", "mihomo.service"],
        ["systemctl", "is-active", "--quiet", "mihomo.service"],
        ["systemctl", "restart", "sg-gateway-singbox.service"],
        ["systemctl", "is-active", "--quiet", "sg-gateway-singbox.service"],
    ]


def test_restart_skips_service_without_applied_config(monkeypatch, tmp_path: Path) -> None:
    module = _load_module()
    mihomo_config = tmp_path / "mihomo.yaml"
    mihomo_config.write_text("mixed-port: 7890\n", encoding="utf-8")
    monkeypatch.setattr(
        module,
        "SERVICES",
        (
            (mihomo_config, "mihomo.service"),
            (tmp_path / "missing.json", "sg-gateway-singbox.service"),
        ),
    )
    calls: list[list[str]] = []
    monkeypatch.setattr(module, "_run", lambda command: calls.append(command))

    payload = module.restart_applied_services()

    assert payload["ok"] is True
    assert payload["services"] == ["mihomo.service"]
    assert all("sg-gateway-singbox.service" not in call for call in calls)


def test_restart_attempts_remaining_service_after_failure(monkeypatch, tmp_path: Path) -> None:
    module = _load_module()
    configs = (tmp_path / "mihomo.yaml", tmp_path / "singbox.json")
    for config in configs:
        config.write_text("{}\n", encoding="utf-8")
    monkeypatch.setattr(
        module,
        "SERVICES",
        (
            (configs[0], "mihomo.service"),
            (configs[1], "sg-gateway-singbox.service"),
        ),
    )
    calls: list[list[str]] = []

    def fake_run(command: list[str]) -> None:
        calls.append(command)
        if command == ["systemctl", "restart", "mihomo.service"]:
            raise RuntimeError("restart failed")

    monkeypatch.setattr(module, "_run", fake_run)

    payload = module.restart_applied_services()

    assert payload["ok"] is False
    assert payload["services"] == ["sg-gateway-singbox.service"]
    assert payload["errors"] == ["mihomo.service: restart failed"]
    assert ["systemctl", "restart", "sg-gateway-singbox.service"] in calls


def test_restart_rejects_when_no_applied_config(monkeypatch, tmp_path: Path) -> None:
    module = _load_module()
    monkeypatch.setattr(
        module,
        "SERVICES",
        (
            (tmp_path / "mihomo.yaml", "mihomo.service"),
            (tmp_path / "singbox.json", "sg-gateway-singbox.service"),
        ),
    )

    try:
        module.restart_applied_services()
    except RuntimeError as exc:
        assert str(exc) == (
            "Применённая конфигурация сервисов отсутствует. "
            "Сначала примените настройки."
        )
    else:
        raise AssertionError("restart must fail without applied configuration")


def test_main_requires_root(monkeypatch, capsys) -> None:
    module = _load_module()
    monkeypatch.setattr(module.os, "geteuid", lambda: 1000)

    assert module.main() == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is False
    assert "root-службу sg-hostd" in payload["message"]


def test_hostd_routes_restart_to_combined_service_helper() -> None:
    source = RUNTIME.read_text(encoding="utf-8")

    assert 'module = "app.mihomo.restart_services" if action == "restart" else "app.mihomo.helper"' in source
    assert '[str(python), "-m", module, action]' in source
