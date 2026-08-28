from __future__ import annotations

import importlib.util
import json
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]
PATCH_PATH = ROOT / "hostd/sg_hostd/xray_stale_profile_patch.py"
SPEC = importlib.util.spec_from_file_location("xray_stale_profile_patch", PATCH_PATH)
assert SPEC is not None and SPEC.loader is not None
PATCH = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PATCH)


@dataclass(frozen=True)
class Profile:
    id: str
    enabled: bool


@dataclass(frozen=True)
class Result:
    engine: str
    ok: bool
    message: str
    clients: int


def _runtime(rows, profiles):
    runtime = SimpleNamespace()
    runtime.EngineResult = Result
    runtime._json = lambda value: json.loads(value) if value else {}
    runtime.xray_profiles_overview = lambda: {
        "profiles": [Profile(profile_id, enabled) for profile_id, enabled in profiles]
    }
    runtime._deployment_rows = lambda engine, active_only=True: list(rows)
    seen = []

    def apply_xray(*, force_profiles=False):
        selected = runtime._deployment_rows("xray")
        seen.extend(selected)
        return Result(
            "xray",
            True,
            f"Xray-профили применены; клиентов: {len(selected)}",
            len(selected),
        )

    runtime._apply_xray = apply_xray
    return runtime, seen


def test_disabled_stale_profile_does_not_fail_xray_apply() -> None:
    rows = [
        {
            "client_id": 9,
            "client_name": "Test9",
            "config_json": json.dumps(
                {"uuid": "test-9", "profiles": ["xhttp_tls"]}
            ),
        }
    ]
    runtime, seen = _runtime(
        rows,
        [("reality_tcp", True), ("xhttp_tls", False)],
    )

    PATCH.install(runtime)
    result = runtime._apply_xray()

    assert result.ok is True
    assert result.clients == 0
    assert seen == []
    assert "Test9" in result.message
    assert "xhttp_tls" in result.message
    assert "выключен на сервере" in result.message


def test_active_profile_is_kept_while_disabled_selection_is_removed() -> None:
    rows = [
        {
            "client_id": 10,
            "client_name": "Mixed",
            "config_json": json.dumps(
                {"uuid": "mixed", "profiles": ["reality_tcp", "xhttp_tls"]}
            ),
        }
    ]
    runtime, seen = _runtime(
        rows,
        [("reality_tcp", True), ("xhttp_tls", False)],
    )

    PATCH.install(runtime)
    result = runtime._apply_xray()

    assert result.ok is True
    assert result.clients == 1
    assert len(seen) == 1
    assert json.loads(seen[0]["config_json"])["profiles"] == ["reality_tcp"]
    assert "xhttp_tls" in result.message
