from __future__ import annotations


def install(commands) -> None:
    if getattr(commands, "_naiveproxy_commands_installed", False):
        return

    def execute(command: str, action: str):
        from sg_hostd import naiveproxy_runtime

        try:
            payload = getattr(naiveproxy_runtime, action)()
        except Exception as exc:
            return commands.HostCommandResult(
                command=command,
                status="error",
                message=str(exc),
                payload={"service": "sg-gateway-naiveproxy.service"},
            )
        return commands.HostCommandResult(
            command=command,
            status="ok" if payload.get("ok", True) else "error",
            message=f"NaiveProxy {action}",
            payload=payload,
        )

    for action in ("sync", "status", "rollback"):
        command = f"naiveproxy.{action}"
        commands._COMMANDS[command] = (
            lambda command=command, action=action: execute(command, action)
        )

    commands._naiveproxy_commands_installed = True
