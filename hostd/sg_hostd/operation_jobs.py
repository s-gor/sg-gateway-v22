from __future__ import annotations

import grp
import json
import os
import secrets
import shlex
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

from app.maintenance.panel_updates import GITHUB_BRANCH

JOB_DIR = Path(
    os.getenv("SG_GATEWAY_OPERATION_JOB_DIR", "/var/lib/sg-gateway/security/jobs")
)
REQUEST = Path(
    os.getenv("SG_GATEWAY_SECURITY_STATE_DIR", "/var/lib/sg-gateway/security")
) / "tls-request.json"
XRAY_CONFIG = Path("/usr/local/etc/xray/config.json")
XRAY_PREVIOUS = XRAY_CONFIG.with_suffix(".json.previous")
RUNNER = Path("/opt/sg-gateway/hostd/sg_hostd/operation_job_runner.py")
PYTHON = Path("/opt/sg-gateway/.venv/bin/python")
PANEL_ACCESS_SCRIPT = Path("/opt/sg-gateway/deploy/configure-panel-access.sh")
PANEL_UPDATE_SCRIPT = Path("/opt/sg-gateway/deploy/update-from-github.sh")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _panel_group() -> int:
    try:
        return grp.getgrnam("sg-gateway").gr_gid
    except KeyError:
        return 0


def _write(path: Path, text: str, mode: int = 0o640) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")
    os.chmod(path, mode)
    try:
        os.chown(path, 0, _panel_group())
    except PermissionError:
        pass


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _runner_command(kind: str, job_id: str) -> tuple[str, ...]:
    return (str(PYTHON), str(RUNNER), kind, job_id)


def _start(
    kind: str,
    title: str,
    target_url: str,
    back_url: str,
    extra: dict[str, Any] | None = None,
    *,
    command: Sequence[str] | None = None,
) -> dict[str, Any]:
    JOB_DIR.mkdir(parents=True, exist_ok=True)
    os.chmod(JOB_DIR, 0o750)
    try:
        os.chown(JOB_DIR, 0, _panel_group())
    except PermissionError:
        pass

    job_id = (
        datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
        + "-"
        + secrets.token_hex(6)
    )
    meta = {
        "kind": kind,
        "title": title,
        "target_url": target_url,
        "back_url": back_url,
        "created_at": _utc_now(),
    }
    if extra:
        meta.update(extra)

    status_path = JOB_DIR / f"{job_id}.status"
    log_path = JOB_DIR / f"{job_id}.log"
    wrapper_path = JOB_DIR / f"{job_id}.sh"
    _write(
        JOB_DIR / f"{job_id}.json",
        json.dumps(meta, ensure_ascii=False, indent=2) + "\n",
    )
    _write(status_path, "queued\n")
    _write(log_path, f"[SG-Gateway] Задача создана: {title}\n")

    command_parts = tuple(command or _runner_command(kind, job_id))
    quoted = " ".join(shlex.quote(item) for item in command_parts)
    wrapper = f"""#!/usr/bin/env bash
set -uo pipefail
export PYTHONPATH=/opt/sg-gateway:/opt/sg-gateway/hostd
export SG_GATEWAY_ENV=production
export SG_GATEWAY_DATA_DIR=/var/lib/sg-gateway
export SG_GATEWAY_LOG_DIR=/var/log/sg-gateway
export SG_GATEWAY_SECURITY_STATE_DIR=/var/lib/sg-gateway/security
export SG_GATEWAY_OPERATION_JOB_DIR=/var/lib/sg-gateway/security/jobs
export SG_GATEWAY_TLS_LIVE_LOG=1
cd /opt/sg-gateway
STATUS={shlex.quote(str(status_path))}
LOG={shlex.quote(str(log_path))}
printf 'running\\n' > "$STATUS"
{{
  echo "[SG-Gateway] Запуск фоновой задачи"
  echo "[SG-Gateway] Время: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
  if {quoted}; then
    printf 'success\\n' > "$STATUS"
    echo "[SG-Gateway] Готово"
  else
    rc=$?
    printf 'failed\\n' > "$STATUS"
    echo "[SG-Gateway] ОШИБКА: код $rc"
    exit "$rc"
  fi
}} >> "$LOG" 2>&1
"""
    _write(wrapper_path, wrapper, 0o750)

    result = subprocess.run(
        [
            "systemd-run",
            "--collect",
            "--unit",
            f"sg-gateway-job-{job_id}",
            "/bin/bash",
            str(wrapper_path),
        ],
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    if result.returncode:
        _write(status_path, "failed\n")
        with log_path.open("a", encoding="utf-8") as stream:
            stream.write(
                (result.stderr or result.stdout or "systemd-run failed") + "\n"
            )
        raise RuntimeError(
            (
                result.stderr
                or result.stdout
                or "Не удалось запустить фоновую задачу"
            ).strip()
        )
    return {
        "ok": True,
        "message": "Фоновая задача запущена",
        "job_id": job_id,
        **meta,
    }


def start_tls_issue_job() -> dict[str, Any]:
    request = _read_json(REQUEST)
    domain = str(request.get("domain") or "").strip()
    if not domain:
        raise RuntimeError("Сначала проверьте домен в Security")
    public_port = int(
        request.get("public_port") or request.get("panel_port") or 443
    )
    if not PANEL_ACCESS_SCRIPT.is_file():
        raise RuntimeError(f"Не найден {PANEL_ACCESS_SCRIPT}")
    suffix = "" if public_port == 443 else f":{public_port}"
    return _start(
        "tls_issue",
        f"Получение сертификата и включение HTTPS · {domain}",
        f"https://{domain}{suffix}/security",
        "/security",
        {"domain": domain, "public_port": public_port},
        command=(
            "/bin/bash",
            str(PANEL_ACCESS_SCRIPT),
            "--mode",
            "https",
            "--host",
            domain,
            "--port",
            str(public_port),
        ),
    )


def run_tls_maintenance(action: str) -> dict[str, Any]:
    if action not in {"renew", "rollback"}:
        raise RuntimeError(f"Неизвестное действие HTTPS: {action}")
    if not PANEL_ACCESS_SCRIPT.is_file():
        raise RuntimeError(f"Не найден {PANEL_ACCESS_SCRIPT}")
    unit = f"sg-gateway-tls-{action}-{secrets.token_hex(4)}"
    result = subprocess.run(
        [
            "systemd-run",
            "--wait",
            "--pipe",
            "--collect",
            "--unit",
            unit,
            "/bin/bash",
            str(PANEL_ACCESS_SCRIPT),
            "--mode",
            action,
        ],
        cwd="/opt/sg-gateway",
        capture_output=True,
        text=True,
        timeout=600 if action == "renew" else 240,
        check=False,
    )
    output = (result.stdout or result.stderr or "").strip()
    if result.returncode:
        raise RuntimeError(output or f"HTTPS {action} failed")
    lines = [line.strip() for line in output.splitlines() if line.strip()]
    return {
        "ok": True,
        "message": lines[-1] if lines else f"HTTPS {action} completed",
        "output": output[-20000:],
    }


def start_full_backup_restore_job() -> dict[str, Any]:
    return _start(
        "full_backup_restore",
        "Полное восстановление SG-Gateway",
        "/maintenance?tab=backups",
        "/maintenance?tab=backups",
        {"restart_expected": True},
    )


def start_xray_apply_job() -> dict[str, Any]:
    return _start(
        "xray_apply",
        "Проверка и применение всех Xray-профилей",
        "/connections#xray-profiles",
        "/connections#xray-profiles",
    )




def start_panel_update_job() -> dict[str, Any]:
    if not PANEL_UPDATE_SCRIPT.is_file():
        raise RuntimeError(f"Не найден {PANEL_UPDATE_SCRIPT}")
    return _start(
        "panel_update_channel",
        f"Безопасное обновление SG-Gateway из GitHub {GITHUB_BRANCH}",
        "/maintenance?tab=updates&refresh=1",
        "/maintenance?tab=updates",
        {"channel": GITHUB_BRANCH, "restart_expected": True},
        command=(
"/usr/bin/env",
f"SG_GATEWAY_GITHUB_BRANCH={GITHUB_BRANCH}",
"/bin/bash",
str(PANEL_UPDATE_SCRIPT),
        ),
    )

def start_core_update_job(engine: str) -> dict[str, Any]:
    if engine not in {"mihomo", "sing-box", "wgcf"}:
        raise RuntimeError(f"Неподдерживаемое ядро: {engine}")
    labels = {"mihomo": "Mihomo", "sing-box": "sing-box", "wgcf": "WARP / wgcf-cli"}
    return _start(
        f"core_update_{engine.replace('-', '_')}",
        f"Безопасное обновление {labels[engine]}",
        "/maintenance?tab=updates&refresh=1",
        "/maintenance?tab=updates",
        {"engine": engine},
    )

def start_xray_update_job(channel: str) -> dict[str, Any]:
    if channel not in {"stable", "prerelease"}:
        raise RuntimeError(f"Неизвестный канал Xray: {channel}")
    label = "стабильной версии" if channel == "stable" else "предварительной версии"
    return _start(
        f"xray_update_{channel}",
        f"Обновление Xray до последней {label}",
        "/maintenance?tab=updates&refresh=1",
        "/maintenance?tab=updates",
        {"channel": channel},
    )


def test_xray_runtime() -> dict[str, Any]:
    if not XRAY_CONFIG.is_file():
        return {"ok": False, "message": "Xray config ещё не создан"}
    result = subprocess.run(
        [
            "/usr/local/bin/xray",
            "run",
            "-test",
            "-config",
            str(XRAY_CONFIG),
        ],
        capture_output=True,
        text=True,
        timeout=90,
        check=False,
    )
    message = (result.stdout or result.stderr or "").strip()
    return {
        "ok": result.returncode == 0,
        "message": message
        or ("Xray config valid" if result.returncode == 0 else "Xray config invalid"),
    }


def rollback_xray_runtime() -> dict[str, Any]:
    if not XRAY_PREVIOUS.is_file():
        raise RuntimeError("Нет предыдущей конфигурации Xray")
    safety = XRAY_CONFIG.with_name("config.json.before-manual-rollback")
    if XRAY_CONFIG.is_file():
        shutil.copy2(XRAY_CONFIG, safety)
    candidate = XRAY_CONFIG.with_name("config.json.rollback-candidate")
    shutil.copy2(XRAY_PREVIOUS, candidate)
    test = subprocess.run(
        [
            "/usr/local/bin/xray",
            "run",
            "-test",
            "-config",
            str(candidate),
        ],
        capture_output=True,
        text=True,
        timeout=90,
        check=False,
    )
    if test.returncode:
        candidate.unlink(missing_ok=True)
        raise RuntimeError(
            (
                test.stderr
                or test.stdout
                or "Предыдущая конфигурация Xray не прошла проверку"
            ).strip()
        )
    os.replace(candidate, XRAY_CONFIG)
    subprocess.run(["systemctl", "restart", "xray.service"], check=True, timeout=60)
    subprocess.run(
        ["systemctl", "is-active", "--quiet", "xray.service"],
        check=True,
        timeout=30,
    )
    return {
        "ok": True,
        "message": "Предыдущая конфигурация Xray восстановлена",
        "safety": str(safety),
    }
