from __future__ import annotations

from flask import Flask, jsonify

from sg_hostd.commands import execute_command, list_allowed_commands
from sg_hostd.dual_stack_runtime import refresh_runtime_metadata
from sg_hostd.full_backup_verify_runtime import verify_uploaded_full_backup


FULL_BACKUP_VERIFY_COMMAND = "backup.full.verify"


def create_app() -> Flask:
    # hostd starts after network-online and runs as root. Refreshing here makes
    # Dual Stack available to every install path, including the vendored FULL
    # package, while IPv6 remains strictly optional.
    dual_stack = refresh_runtime_metadata()
    app = Flask(__name__)

    @app.get("/health")
    def health():
        return jsonify({
            "service": "sg-hostd",
            "status": "ok",
            "dual_stack": bool(dual_stack.get("dual_stack")),
            "ipv4": bool(dual_stack.get("ipv4")),
            "ipv6": bool(dual_stack.get("ipv6")),
        })

    @app.get("/commands")
    def commands():
        allowed = sorted(set(list_allowed_commands()) | {FULL_BACKUP_VERIFY_COMMAND})
        return jsonify({"commands": allowed})

    @app.post("/commands/<path:command>")
    def run_command(command: str):
        if command == FULL_BACKUP_VERIFY_COMMAND:
            try:
                payload = verify_uploaded_full_backup()
                return jsonify({
                    "command": command,
                    "status": "ok",
                    "message": "Full backup verification passed",
                    "payload": payload,
                }), 200
            except Exception as exc:
                return jsonify({
                    "command": command,
                    "status": "error",
                    "message": f"Full backup verification failed: {exc}",
                    "payload": {},
                }), 403

        result = execute_command(command)
        status_code = 200 if result.status != "error" else 403
        return jsonify(
            {
                "command": result.command,
                "status": result.status,
                "message": result.message,
                "payload": result.payload,
            }
        ), status_code

    return app


app = create_app()
