from __future__ import annotations

import os
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]
INSTALL = (ROOT / "install.sh").read_text(encoding="utf-8")
BUILD = (ROOT / "build-run.sh").read_text(encoding="utf-8")


def _function(name: str) -> str:
    match = re.search(rf"(?ms)^{re.escape(name)}\(\) \{{\n.*?^\}}\n", INSTALL)
    assert match, name
    return match.group(0)


def test_systemctl_retry_recovers_after_transient_bus_failure(tmp_path: Path) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    state = tmp_path / "count"
    log = tmp_path / "installer.log"
    (bin_dir / "systemctl").write_text(
        """#!/usr/bin/env bash
set -u
if [[ "${1:-}" == "daemon-reload" ]]; then
  exit 0
fi
count=0
[[ ! -f "$SG_TEST_STATE" ]] || count="$(cat "$SG_TEST_STATE")"
count=$((count + 1))
printf '%s' "$count" > "$SG_TEST_STATE"
if (( count == 1 )); then
  echo 'Transport endpoint is not connected' >&2
  exit 1
fi
exit 0
""",
        encoding="utf-8",
    )
    (bin_dir / "sleep").write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
    os.chmod(bin_dir / "systemctl", 0o755)
    os.chmod(bin_dir / "sleep", 0o755)
    script = f"""set -Eeuo pipefail
INSTALL_LOG={log!s}
{_function('systemctl_with_retry')}
systemctl_with_retry enable --now nginx.service
"""
    env = os.environ.copy()
    env["PATH"] = f"{bin_dir}:{env['PATH']}"
    env["SG_TEST_STATE"] = str(state)
    env["SG_GATEWAY_SYSTEMCTL_RETRY_DELAY"] = "0"
    result = subprocess.run(["bash", "-c", script], env=env, text=True, capture_output=True)
    assert result.returncode == 0, result.stderr
    assert state.read_text(encoding="utf-8") == "2"
    assert "attempt 1/5 failed" in log.read_text(encoding="utf-8")


def test_systemctl_retry_does_not_mask_real_failure(tmp_path: Path) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    log = tmp_path / "installer.log"
    (bin_dir / "systemctl").write_text(
        "#!/usr/bin/env bash\n[[ \"${1:-}\" == daemon-reload ]] && exit 0\nexit 9\n",
        encoding="utf-8",
    )
    (bin_dir / "sleep").write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
    os.chmod(bin_dir / "systemctl", 0o755)
    os.chmod(bin_dir / "sleep", 0o755)
    script = f"""set -Eeuo pipefail
INSTALL_LOG={log!s}
{_function('systemctl_with_retry')}
systemctl_with_retry enable --now nginx.service
"""
    env = os.environ.copy()
    env["PATH"] = f"{bin_dir}:{env['PATH']}"
    env["SG_GATEWAY_SYSTEMCTL_RETRY_ATTEMPTS"] = "3"
    env["SG_GATEWAY_SYSTEMCTL_RETRY_DELAY"] = "0"
    result = subprocess.run(["bash", "-c", script], env=env, text=True, capture_output=True)
    assert result.returncode == 9
    assert log.read_text(encoding="utf-8").count("systemctl attempt") == 3


def test_final_stage_mutations_use_retry_wrapper() -> None:
    required = (
        "systemctl_with_retry enable --now sg-hostd.service",
        "systemctl_with_retry enable --now sg-gateway.service",
        "systemctl_with_retry enable --now nginx.service",
        "systemctl_with_retry enable xray.service",
        "systemctl_with_retry restart xray.service",
    )
    for text in required:
        assert text in INSTALL, text


def test_build_acceptance_guards_restored() -> None:
    for text in (
        "SG_DEVICE_EXPANDED_CLEANUP_V1_LAST_CSS",
        "recovery_restore_backup_route(name: str)",
        "data-recovery-restore",
        "SOURCE-SHA256SUMS missing files",
        "sg-device-expanded-cleanup-v1.css",
        "sg-recovery-restore-v1.css",
    ):
        assert text in BUILD, text
