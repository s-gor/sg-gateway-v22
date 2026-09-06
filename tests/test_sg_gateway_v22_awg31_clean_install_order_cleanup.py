from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _run_bash(script: str, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", "-c", script, "bash", *args],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )


def test_awg31_stage3a_precedes_first_clean_install_clients_apply() -> None:
    source = (ROOT / "install.sh").read_text(encoding="utf-8")
    main = source[source.index("main() {"):]
    awg31 = 'run_stage 19 "Независимый профиль AWG31" run_awg31_stage3a_migration'
    clients = 'run_stage 20 "Применение Xray и клиентов" stage9_apply_runtime'
    assert awg31 in main
    assert clients in main
    assert main.index(awg31) < main.index(clients)


def _extract_shell_function(source: str, name: str) -> str:
    start = source.index(f"{name}(){{")
    tail = source[start:]
    end_marker = "\n}\n"
    end = tail.index(end_marker) + len(end_marker)
    return tail[:end]


def test_account_removal_cannot_leave_or_recreate_data_directory(tmp_path: Path) -> None:
    source = (ROOT / "deploy/full-uninstall-ubuntu.sh").read_text(encoding="utf-8")
    function = _extract_shell_function(source, "remove_account_and_verify")
    data_dir = tmp_path / "var/lib/sg-gateway"
    harness = rf'''
set -Eeuo pipefail
PREFIX="$1/opt/sg-gateway"
CONFIG_DIR="$1/etc/sg-gateway"
DATA_DIR="$1/var/lib/sg-gateway"
LOG_DIR="$1/var/log/sg-gateway"
user_present=1
group_present=1

id() {{ (( user_present == 1 )); }}
userdel() {{
  user_present=0
  mkdir -p "$DATA_DIR"
}}
getent() {{ (( group_present == 1 )); }}
groupdel() {{ group_present=0; }}
systemctl() {{ :; }}

{function}

rm -rf "$PREFIX" "$CONFIG_DIR" "$DATA_DIR"
remove_account_and_verify
[[ ! -e "$DATA_DIR" ]]
(( user_present == 0 ))
(( group_present == 0 ))
'''
    result = _run_bash(harness, str(tmp_path))
    assert result.returncode == 0, result.stderr + result.stdout
    assert not data_dir.exists()
