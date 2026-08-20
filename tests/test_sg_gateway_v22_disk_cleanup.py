from __future__ import annotations

import os
import time
from pathlib import Path
from types import SimpleNamespace

from flask import Flask

import app.system_disk_cleanup_http as cleanup_http
from sg_hostd import disk_cleanup


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


def test_disk_cleanup_ui_is_wired_to_safe_post_action() -> None:
    javascript = (
        ROOT / "app" / "web" / "static" / "sg-disk-breakdown-v2.js"
    ).read_text(encoding="utf-8")
    production = (ROOT / "app" / "production.py").read_text(encoding="utf-8")
    hostd = (ROOT / "hostd" / "sg_hostd" / "app.py").read_text(encoding="utf-8")

    assert 'form.action = "/system/disk/cleanup"' in javascript
    assert "window.confirm" in javascript
    assert "register_system_disk_cleanup(app)" in production
    assert 'SYSTEM_DISK_CLEANUP_COMMAND = "system.disk.cleanup.start"' in hostd
    assert "autoremove" not in (ROOT / "hostd" / "sg_hostd" / "disk_cleanup.py").read_text(
        encoding="utf-8"
    )
