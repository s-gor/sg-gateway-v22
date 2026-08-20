from __future__ import annotations

import os
import sys
import time
from pathlib import Path
from types import SimpleNamespace

from flask import Flask

import app.system_disk_cleanup_http as cleanup_http
from sg_hostd import disk_cleanup, operation_job_runner


ROOT = Path(__file__).resolve().parents[1]


def test_system_disk_cleanup_http_starts_live_terminal(monkeypatch) -> None:
    app = Flask(__name__)
    app.secret_key = "test"

    @app.get("/system")
    def system():
        return "system"

    cleanup_http.register_system_disk_cleanup(app)
    monkeypatch.setattr(
        cleanup_http,
        "run_hostd_command",
        lambda command, timeout=20: SimpleNamespace(
            status="ok",
            message="started",
            payload={"job_id": "20260820150000-abcdef123456"},
        ),
    )

    response = app.test_client().post("/system/disk/cleanup")
    assert response.status_code == 302
    assert response.headers["Location"].endswith(
        "/system/disk/cleanup/20260820150000-abcdef123456"
    )


def test_disk_cleanup_removes_only_stale_operation_job_files(
    monkeypatch,
    tmp_path: Path,
) -> None:
    old_log = tmp_path / "old.log"
    new_log = tmp_path / "new.log"
    unrelated = tmp_path / "keep.txt"
    old_log.write_bytes(b"old terminal")
    new_log.write_bytes(b"new terminal")
    unrelated.write_bytes(b"unrelated")

    stale = time.time() - 30 * 86400
    os.utime(old_log, (stale, stale))
    os.utime(unrelated, (stale, stale))

    monkeypatch.setattr(disk_cleanup, "JOB_DIR", tmp_path)
    removed, removed_bytes = disk_cleanup._cleanup_old_job_files(days=14)

    assert removed == 1
    assert removed_bytes == len(b"old terminal")
    assert not old_log.exists()
    assert new_log.exists()
    assert unrelated.exists()


def test_disk_cleanup_job_uses_shared_operation_runner(monkeypatch) -> None:
    captured: dict = {}

    def fake_start(*args, **kwargs):
        captured["args"] = args
        captured["kwargs"] = kwargs
        return {"job_id": "20260820150000-abcdef123456"}

    monkeypatch.setattr(disk_cleanup, "_start", fake_start)
    result = disk_cleanup.start_disk_cleanup_job()

    assert result["job_id"] == "20260820150000-abcdef123456"
    assert captured["args"][0] == "disk_cleanup"
    assert captured["kwargs"] == {}


def test_operation_job_runner_dispatches_disk_cleanup(monkeypatch) -> None:
    called = {"count": 0}

    def fake_cleanup() -> int:
        called["count"] += 1
        return 0

    monkeypatch.setattr(disk_cleanup, "run_disk_cleanup", fake_cleanup)
    monkeypatch.setattr(
        sys,
        "argv",
        ["operation_job_runner.py", "disk_cleanup", "20260820150000-abcdef123456"],
    )

    assert operation_job_runner.main() == 0
    assert called["count"] == 1


def test_disk_cleanup_ui_is_wired_to_safe_post_action() -> None:
    javascript = (
        ROOT / "app" / "web" / "static" / "sg-disk-breakdown-v2.js"
    ).read_text(encoding="utf-8")
    production = (ROOT / "app" / "production.py").read_text(encoding="utf-8")
    hostd = (ROOT / "hostd" / "sg_hostd" / "app.py").read_text(encoding="utf-8")
    cleanup_source = (
        ROOT / "hostd" / "sg_hostd" / "disk_cleanup.py"
    ).read_text(encoding="utf-8")
    runner_source = (
        ROOT / "hostd" / "sg_hostd" / "operation_job_runner.py"
    ).read_text(encoding="utf-8")

    assert 'form.action = "/system/disk/cleanup"' in javascript
    assert "window.confirm" in javascript
    assert "register_system_disk_cleanup(app)" in production
    assert 'SYSTEM_DISK_CLEANUP_COMMAND = "system.disk.cleanup.start"' in hostd
    assert "autoremove" not in cleanup_source
    assert "command=(str(PYTHON)" not in cleanup_source
    assert 'if sys.argv[1] == "disk_cleanup"' in runner_source
