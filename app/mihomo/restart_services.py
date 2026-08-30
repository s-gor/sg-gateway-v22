from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


SERVICES: tuple[tuple[Path, str], ...] = (
    (Path("/etc/mihomo/config.yaml"), "mihomo.service"),
    (Path("/etc/sing-box/config.json"), "sg-gateway-singbox.service"),
)


def _result(ok: bool, message: str, **extra: object) -> dict[str, object]:
    return {"ok": ok, "message": message, **extra}


def _require_root() -> None:
    if os.geteuid() != 0:
        raise RuntimeError(
            "Перезапуск применённых сервисов доступен только через root-службу sg-hostd"
        )


def _run(command: list[str]) -> None:
    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(
            (result.stderr or result.stdout).strip()
            or f"Команда завершилась с кодом {result.returncode}"
        )


def restart_applied_services() -> dict[str, object]:
    applied = [(config, service) for config, service in SERVICES if config.is_file()]
    if not applied:
        raise RuntimeError(
            "Применённая конфигурация сервисов отсутствует. "
            "Сначала примените настройки."
        )

    restarted: list[str] = []
    errors: list[str] = []
    for _config, service in applied:
        try:
            _run(["systemctl", "restart", service])
            _run(["systemctl", "is-active", "--quiet", service])
            restarted.append(service)
        except Exception as exc:
            errors.append(f"{service}: {exc}")

    if errors:
        return _result(
            False,
            "Не удалось перезапустить все применённые сервисы",
            services=restarted,
            errors=errors,
        )
    return _result(True, "Сервисы перезапущены", services=restarted)


def main() -> int:
    action = sys.argv[1] if len(sys.argv) > 1 else "restart"
    try:
        _require_root()
        if action != "restart":
            raise RuntimeError("Допустимое действие: restart")
        payload = restart_applied_services()
    except Exception as exc:
        print(json.dumps(_result(False, str(exc)), ensure_ascii=False))
        return 1

    print(json.dumps(payload, ensure_ascii=False))
    return 0 if bool(payload.get("ok")) else 1


if __name__ == "__main__":
    raise SystemExit(main())
