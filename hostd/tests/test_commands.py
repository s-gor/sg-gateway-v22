from sg_hostd.commands import execute_command, list_allowed_commands


def test_allowed_commands_are_explicit():
    commands = list_allowed_commands()

    assert "awg.status" in commands
    assert "system.diagnostics" in commands


def test_unknown_command_is_rejected():
    result = execute_command("shell.rm")

    assert result.status == "error"
    assert result.message == "Command is not allowed"