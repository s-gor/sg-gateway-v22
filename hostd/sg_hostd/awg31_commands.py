from __future__ import annotations


def install(commands) -> None:
    if getattr(commands, "_awg31_commands_installed", False):
        return

    def control(command: str, action: str):
        from sg_hostd import awg31_runtime

        try:
            payload = awg31_runtime.control(action)
        except Exception as exc:
            return commands.HostCommandResult(
                command=command,
                status="error",
                message=str(exc),
                payload={"service": "sg-gateway-awg31.service"},
            )
        return commands.HostCommandResult(
            command=command,
            status="ok" if payload.get("ok", True) else "error",
            message=f"AWG31 service {action}",
            payload={"service": "sg-gateway-awg31.service", **payload},
        )

    for action in ("start", "stop", "restart", "status"):
        command = f"awg31.{action}"
        commands._COMMANDS[command] = (
            lambda command=command, action=action: control(command, action)
        )
    commands._awg31_commands_installed = True
