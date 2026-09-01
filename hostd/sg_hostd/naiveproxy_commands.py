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

    original_clients_apply = commands._COMMANDS.get("clients.apply")
    if original_clients_apply is not None:
        def clients_apply():
            base = original_clients_apply()
            if base.status != "ok":
                return base

            from sg_hostd import naiveproxy_runtime
            try:
                settings, users, credential_ids = naiveproxy_runtime._load()
                configured = bool(str(settings.get("domain") or "").strip())
                if not configured and not credential_ids:
                    return base
                payload = naiveproxy_runtime.sync()
            except Exception as exc:
                return commands.HostCommandResult(
                    command="clients.apply",
                    status="error",
                    message=f"NaiveProxy: {exc}",
                    payload={
                        "base_runtime": dict(base.payload),
                        "service": "sg-gateway-naiveproxy.service",
                    },
                )

            combined = dict(base.payload)
            combined["naiveproxy"] = {
                "service": str(
                    payload.get("service")
                    or "sg-gateway-naiveproxy.service"
                ),
                "port": int(payload.get("port") or settings.get("port") or 8447),
                "users": int(payload.get("users") or len(users)),
                "credentials": len(credential_ids),
            }
            return commands.HostCommandResult(
                command="clients.apply",
                status="ok",
                message=(base.message or "Client runtime applied") + "; NaiveProxy applied",
                payload=combined,
            )

        commands._COMMANDS["clients.apply"] = clients_apply

    commands._naiveproxy_commands_installed = True
