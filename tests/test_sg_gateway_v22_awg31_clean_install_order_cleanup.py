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


@pytest.mark.parametrize("installer", ["install.sh", "deploy/install-core.sh"])
def test_awg31_stage3a_precedes_first_clean_install_clients_apply(
    tmp_path: Path, installer: str
) -> None:
    trace = tmp_path / "trace.log"
    harness = r'''
set -Eeuo pipefail
source "$1"
TRACE="$2"
TMP_ROOT="$3"
RESUME_FILE="$TMP_ROOT/resume.env"
BACKUP_ROOT="$TMP_ROOT/backups"
INSTALL_LOG="$TMP_ROOT/install.log"
mkdir -p "$BACKUP_ROOT"

record() { printf '%s\n' "$1" >> "$TRACE"; }
require_root() { :; }
require_supported_ubuntu() { :; }
prepare_log() { : > "$INSTALL_LOG"; }
bootstrap_packages() { :; }
verify_vendor_core_set() { :; }
detect_existing_install() { return 1; }
detect_minimal_013_install() { return 1; }
load_resume_state() { return 0; }
collect_automatic_parameters() { :; }
save_resume_state() { :; }
run_stage() { :; }
run_quiet() { shift; "$@"; }
stage9_start_hostd() { record hostd.start; }
stage9_verify_hostd() { record hostd.verify; }
run_awg31_stage3a_migration() { record awg31.stage3a; }
stage9_apply_runtime() { record clients.apply; }
stage9_start_panel() { record panel.start; }
stage9_verify_nginx() { record nginx.verify; }
verify_client_identities_after_update() { :; }
sanitize_installer_log_file() { :; }
saved_https_access() { :; }
xray_installed_version() { printf 'test'; }
print_sg_admin_status() { :; }
rm() { :; }

main >/dev/null
cat "$TRACE"
'''
    result = _run_bash(
        harness,
        str(ROOT / installer),
        str(trace),
        str(tmp_path),
    )
    assert result.returncode == 0, result.stderr
    calls = result.stdout.splitlines()
    assert calls.count("awg31.stage3a") == 1, calls
    assert calls.count("clients.apply") == 1, calls
    assert calls.index("awg31.stage3a") < calls.index("clients.apply"), calls


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
