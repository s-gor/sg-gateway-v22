from types import SimpleNamespace

from sg_hostd import clients_keys_portable_restore_patch as patch


class _ProbeResult:
    def __init__(self, returncode=0, stdout='{"ok": true, "engine": "xray"}'):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = ""


class _Full:
    def __init__(self):
        self.commands = []

    def _runtime_subprocess_env(self):
        return {"PYTHONPATH": "/opt/sg-gateway"}

    def _probe(self, command, *, timeout, env):
        self.commands.append((command, timeout, env))
        return _ProbeResult()


def test_clients_keys_restore_reapplies_enabled_reality_after_policy_status_restore(monkeypatch):
    helper = getattr(patch, "_apply_restored_xray_profiles_required", None)
    assert callable(helper), "restore is missing the post-policy Xray profile reconcile"

    monkeypatch.setattr(patch.Path, "is_file", lambda self: True)
    full = _Full()
    policy = {
        "settings": {"xray": True},
        "xray_profiles": ["reality_tcp", "xhttp_reality"],
    }

    result = helper(full, policy)

    assert result["ok"] is True
    assert len(full.commands) == 1
    command, timeout, env = full.commands[0]
    assert timeout == 180
    assert env["SG_GATEWAY_CLIENTS_KEYS_RESTORE"] == "1"
    assert "apply_xray_runtime(force_profiles=True)" in command[-1]


def test_clients_keys_restore_does_not_force_xray_when_destination_disabled(monkeypatch):
    helper = getattr(patch, "_apply_restored_xray_profiles_required", None)
    assert callable(helper), "restore is missing the post-policy Xray profile reconcile"

    monkeypatch.setattr(patch.Path, "is_file", lambda self: True)
    full = _Full()
    policy = {
        "settings": {"xray": False},
        "xray_profiles": ["reality_tcp", "xhttp_reality"],
    }

    result = helper(full, policy)

    assert result == {"ok": True, "skipped": True, "reason": "xray-disabled"}
    assert full.commands == []
