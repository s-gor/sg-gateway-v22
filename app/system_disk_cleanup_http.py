from __future__ import annotations

from flask import Flask, abort, flash, redirect, render_template, url_for

from app.hostd.client import run_hostd_command
from app.security.operation_jobs import read_job as read_operation_job


DISK_CLEANUP_COMMAND = "system.disk.cleanup.start"


def register_system_disk_cleanup(app: Flask) -> None:
    if "system_disk_cleanup_start" in app.view_functions:
        return

    @app.post("/system/disk/cleanup")
    def system_disk_cleanup_start():
        result = run_hostd_command(DISK_CLEANUP_COMMAND, timeout=20)
        if result.status != "ok":
            flash(
                f"Очистка диска не запущена: {result.message or 'sg-hostd отклонил задачу'}",
                "error",
            )
            return redirect(url_for("system") + "?disk_refresh=1")

        job_id = str(result.payload.get("job_id") or "")
        if not job_id:
            flash("Очистка диска не запущена: sg-hostd не вернул ID задачи.", "error")
            return redirect(url_for("system") + "?disk_refresh=1")

        return redirect(url_for("system_disk_cleanup_job", job_id=job_id))

    @app.get("/system/disk/cleanup/<job_id>")
    def system_disk_cleanup_job(job_id: str):
        try:
            job = read_operation_job(job_id)
        except FileNotFoundError:
            abort(404)
        if str(job.get("kind") or "") != "disk_cleanup":
            abort(404)
        return render_template(
            "operation_job.html",
            active_page="system",
            job=job,
        )
