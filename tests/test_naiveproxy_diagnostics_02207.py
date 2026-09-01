from __future__ import annotations

import hashlib
import importlib.util
from pathlib import Path
from types import SimpleNamespace


MODULE_PATH = (
    Path(__file__).parents[1]
    / "hostd"
    / "sg_hostd"
    / "naiveproxy_diagnostics_patch.py"
)
SPEC = importlib.util.spec_from_file_location(
    "naiveproxy_diagnostics_patch_test", MODULE_PATH
)
diagnostics_patch = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(diagnostics_patch)


def _runtime(tmp_path: Path, *, expected_sha: str | None = None):
    prefix = tmp_path / "naiveproxy"
    binary = prefix / "bin" / "caddy"
    binary.parent.mkdir(parents=True)
    binary.write_bytes(b"pinned-caddy-binary")
    actual_sha = hashlib.sha256(binary.read_bytes()).hexdigest()
    (prefix / "VERSIONS.env").write_text(
        "\n".join(
            (
                "RUNTIME_VERSION=v2.11.2-naive",
                f"RUNTIME_SHA256={expected_sha or actual_sha}",
                "RUNTIME_URL=https://example.invalid/caddy.tar.xz",
            )
        )
        + "\n",
        encoding="utf-8",
    )
    config = tmp_path / "Caddyfile"
    config.write_text(":8447 {}\n", encoding="utf-8")
    state = tmp_path / "state.json"
    state.write_text(
        '{"settings":{"port":8447},"users":2,'
        '"firewall":{"active":true,"managed":true,"port":8447}}\n',
        encoding="utf-8",
    )

    def run(command, timeout=30):
        if command[:2] == [str(binary), "version"]:
            return SimpleNamespace(
                returncode=0,
                stdout="v2.11.2 h1:test\n",
                stderr="",
            )
        if len(command) >= 2 and command[0] == str(binary) and command[1] == "validate":
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        if command[:3] == ["ss", "-H", "-ltnp"]:
            return SimpleNamespace(
                returncode=0,
                stdout='LISTEN 0 4096 0.0.0.0:8447 0.0.0.0:* users:(("caddy",pid=7,fd=3))\n',
                stderr="",
            )
        raise AssertionError(command)

    return SimpleNamespace(
        BINARY=binary,
        CONFIG_PATH=config,
        STATE_PATH=state,
        DEFAULT_PORT=8447,
        _run=run,
        _redact=lambda value: str(value),
        status=lambda: {
            "ok": True,
            "active": True,
            "service": "sg-gateway-naiveproxy.service",
            "port": 8447,
            "users": 2,
        },
    )


def test_status_verifies_binary_config_listener_and_firewall(tmp_path):
    runtime = _runtime(tmp_path)
    diagnostics_patch.install(runtime)

    result = runtime.status()

    assert result["ok"] is True
    assert result["installed"] is True
    assert result["runtime_release"] == "v2.11.2-naive"
    assert result["runtime_version"] == "v2.11.2 h1:test"
    assert result["checksum_ok"] is True
    assert result["config_valid"] is True
    assert result["listener"] == {
        "listening": True,
        "owned_by_caddy": True,
    }
    assert result["firewall"] == {
        "active": True,
        "managed": True,
        "port": 8447,
    }


def test_status_fails_closed_on_checksum_mismatch(tmp_path):
    runtime = _runtime(tmp_path, expected_sha="0" * 64)
    diagnostics_patch.install(runtime)

    result = runtime.status()

    assert result["checksum_ok"] is False
    assert result["ok"] is False


def test_diagnostics_payload_contains_no_credentials(tmp_path):
    runtime = _runtime(tmp_path)
    diagnostics_patch.install(runtime)

    rendered = repr(runtime.status()).lower()

    assert "username" not in rendered
    assert "password" not in rendered
    assert "basic_auth" not in rendered
