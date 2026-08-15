from __future__ import annotations

from flask import Flask, jsonify

from sg_hostd.commands import execute_command, list_allowed_commands


def create_app() -> Flask:
    app = Flask(__name__)

    @app.get("/health")
    def health():
        return jsonify({"service": "sg-hostd", "status": "ok"})

    @app.get("/commands")
    def commands():
        return jsonify({"commands": list_allowed_commands()})

    @app.post("/commands/<path:command>")
    def run_command(command: str):
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