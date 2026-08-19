from __future__ import annotations

import json
import os
import subprocess
import sys
import traceback
from pathlib import Path


# This module is executed directly from hostd/sg_hostd. The sibling app.py
# must never shadow the real /opt/sg-gateway/app package.
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_HOSTD_ROOT = _PROJECT_ROOT / "hostd"
_SCRIPT_DIR = Path(__file__).resolve().parent

for _entry in (str(_SCRIPT_DIR), str(_HOSTD_ROOT), str(_PROJECT_ROOT)):
    while _entry in sys.path:
        sys.path.remove(_entry)
sys.path[:0] = [str(_PROJECT_ROOT), str(_HOSTD_ROOT)]

os.environ.setdefault("SG_GATEWAY_ENV", "production")
os.environ.setdefault("SG_GATEWAY_DATA_DIR", "/var/lib/sg-gateway")
os.environ.setdefault("SG_GATEWAY_LOG_DIR", "/var/log/sg-gateway")
os.environ.setdefault(
    "SG_GATEWAY_SECURITY_STATE_DIR",
    "/var/lib/sg-gateway/security",
)
os.environ.setdefault(
    "SG_GATEWAY_OPERATION_JOB_DIR",
    "/var/log/sg-gateway/operation-jobs",
)
os.chdir(_PROJECT_ROOT)


def _dump(value) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2, default=str), flush=True)


def run_xray() -> int:
    from app.xray.profiles import overview
    from sg_hostd.client_runtime import _apply_xray

    state = overview()
    print("[Xray 1/4] Независимые профили:", flush=True)
    for item in state["profiles"]:
        flow = f"; flow {item.flow}" if getattr(item, "flow", "") else ""
        print(
            f"  - {item.title}: {item.status}; {item.transport}; "
            f"порт {item.port}{flow}",
            flush=True,
        )
    print("[Xray 2/4] Собираю единый candidate config.json", flush=True)
    print("[Xray 3/4] Выполняю xray run -test и атомарное применение", flush=True)
    result = _apply_xray()
    _dump(result.__dict__ if hasattr(result, "__dict__") else result)
    if not getattr(result, "ok", False):
        raise RuntimeError(getattr(result, "message", "Xray apply failed"))
    print("[Xray 4/4] Служба Xray проверена", flush=True)
    return 0


def run_xray_update(channel: str) -> int:
    from sg_hostd.xray_update_runtime import update_xray

    print("[Xray Update] Подготавливаю безопасное обновление", flush=True)
    result = update_xray(channel)
    _dump(result)
    return 0




def run_panel_update() -> int:
    from app.maintenance.panel_updates import GITHUB_BRANCH

    script = _PROJECT_ROOT / "deploy" / "update-from-github.sh"
    if not script.is_file():
        raise RuntimeError(f"Не найден {script}")
    env = dict(os.environ)
    env["SG_GATEWAY_GITHUB_BRANCH"] = GITHUB_BRANCH
    print(f"[SG-Gateway Update] Запускаю проверенный updater · channel {GITHUB_BRANCH}", flush=True)
    completed = subprocess.run(
        ["/bin/bash", str(script)],
        cwd=str(_PROJECT_ROOT),
        env=env,
        check=False,
    )
    return int(completed.returncode)

def run_core_update(engine: str) -> int:
    from sg_hostd.core_update_runtime import update_core

    print(f"[Core Update] Подготавливаю безопасное обновление {engine}", flush=True)
    _dump(update_core(engine))
    return 0

def run_full_backup_restore() -> int:
    from sg_hostd.full_backup_runtime import restore_uploaded_full_backup

    print("[Full Restore] Фоновая транзакция запущена", flush=True)
    result = restore_uploaded_full_backup()
    _dump(result)
    return 0


def main() -> int:
    if len(sys.argv) != 3:
        return 2
    try:
        if sys.argv[1] == "full_backup_restore":
            return run_full_backup_restore()
        if sys.argv[1] == "xray_apply":
            return run_xray()
        if sys.argv[1] == "xray_update_stable":
            return run_xray_update("stable")
        if sys.argv[1] == "xray_update_prerelease":
            return run_xray_update("prerelease")
        if sys.argv[1] == "panel_update_main":
            return run_panel_update()
        if sys.argv[1] == "core_update_mihomo":
            return run_core_update("mihomo")
        if sys.argv[1] == "core_update_sing_box":
            return run_core_update("sing-box")
        if sys.argv[1] == "core_update_wgcf":
            return run_core_update("wgcf")
        raise RuntimeError(f"Неизвестный тип задачи: {sys.argv[1]}")
    except Exception as exc:
        print(f"[SG-Gateway] ОШИБКА: {exc}", file=sys.stderr, flush=True)
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
