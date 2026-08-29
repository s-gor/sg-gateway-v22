from __future__ import annotations

import os
from pathlib import Path
import re
import shlex
import subprocess


ROOT = Path(__file__).resolve().parents[1]
INSTALL = (ROOT / "install.sh").read_text(encoding="utf-8")


def _function(name: str) -> str:
    match = re.search(rf"(?ms)^{re.escape(name)}\(\) \{{\n.*?^\}}\n", INSTALL)
    assert match, name
    return match.group(0)


def _fake_runtime(tmp_path: Path) -> tuple[Path, Path, Path]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    state = tmp_path / "login-count"
    log = tmp_path / "installer.log"

    (bin_dir / "curl").write_text(
        """#!/usr/bin/env bash
set -u
out=""
url=""
while (($#)); do
  case "$1" in
    -o) out="$2"; shift 2 ;;
    -w) shift 2 ;;
    --max-time|--connect-timeout) shift 2 ;;
    -sS|-fsS) shift ;;
    *) url="$1"; shift ;;
  esac
done
if [[ "$url" == */health ]]; then
  if [[ -n "$out" && "$out" != /dev/null ]]; then
    printf '%s' '{"service":"sg-gateway-panel","status":"ok"}' > "$out"
  fi
  printf '200'
  exit 0
fi
count=0
[[ ! -f "$SG_TEST_STATE" ]] || count="$(cat "$SG_TEST_STATE")"
count=$((count + 1))
printf '%s' "$count" > "$SG_TEST_STATE"
success_after="${SG_TEST_LOGIN_SUCCESS_AFTER:-0}"
if (( success_after > 0 && count >= success_after )); then
  printf '200'
  exit 0
fi
printf '000'
exit 28
""",
        encoding="utf-8",
    )
    (bin_dir / "systemctl").write_text(
        """#!/usr/bin/env bash
if [[ "${1:-}" == "is-active" ]]; then
  echo active
  exit 0
fi
exit 0
""",
        encoding="utf-8",
    )
    (bin_dir / "ss").write_text(
        "#!/usr/bin/env bash\necho 'LISTEN 0 128 127.0.0.1:18080 0.0.0.0:*'\n",
        encoding="utf-8",
    )
    (bin_dir / "sleep").write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
    for path in bin_dir.iterdir():
        os.chmod(path, 0o755)
    return bin_dir, state, log


def _run_stage(
    tmp_path: Path,
    *,
    login_success_after: int,
    primary_attempts: int = 15,
    final_attempts: int = 3,
) -> tuple[subprocess.CompletedProcess[str], str, int]:
    bin_dir, state, log = _fake_runtime(tmp_path)
    script = f"""set -Eeuo pipefail
INSTALL_LOG={shlex.quote(str(log))}
BACKEND_PORT=18080
{_function('systemctl_with_retry')}
{_function('http_wait_json')}
{_function('http_wait_login')}
{_function('panel_startup_final_recheck')}
{_function('panel_startup_verify')}
{_function('stage9_start_panel')}
stage9_start_panel
"""
    env = os.environ.copy()
    env["PATH"] = f"{bin_dir}:{env['PATH']}"
    env["SG_TEST_STATE"] = str(state)
    env["SG_TEST_LOGIN_SUCCESS_AFTER"] = str(login_success_after)
    env["SG_GATEWAY_LOGIN_RETRY_ATTEMPTS"] = str(primary_attempts)
    env["SG_GATEWAY_LOGIN_RETRY_DELAY"] = "0"
    env["SG_GATEWAY_LOGIN_REQUEST_TIMEOUT"] = "1"
    env["SG_GATEWAY_FINAL_RECHECK_ATTEMPTS"] = str(final_attempts)
    env["SG_GATEWAY_SYSTEMCTL_RETRY_DELAY"] = "0"
    result = subprocess.run(
        ["bash", "-c", script],
        env=env,
        text=True,
        capture_output=True,
    )
    body = log.read_text(encoding="utf-8") if log.exists() else ""
    count = int(state.read_text(encoding="utf-8")) if state.exists() else 0
    return result, body, count


def test_login_timeout_recovers_inside_primary_retry_window(tmp_path: Path) -> None:
    result, log, count = _run_stage(
        tmp_path,
        login_success_after=3,
        primary_attempts=5,
        final_attempts=2,
    )
    assert result.returncode == 0, result.stderr
    assert count == 3
    assert "Login attempt 1/5: service=active; HTTP 000; curl rc=28" in log
    assert "Login attempt 2/5: service=active; HTTP 000; curl rc=28" in log
    assert "Login OK: service=active; HTTP 200; curl rc=0; attempt 3/5" in log
    assert "Primary panel startup check did not settle" not in log


def test_final_recheck_can_recover_before_rollback(tmp_path: Path) -> None:
    result, log, count = _run_stage(
        tmp_path,
        login_success_after=3,
        primary_attempts=2,
        final_attempts=2,
    )
    assert result.returncode == 0, result.stderr
    assert count == 3
    assert "Primary panel startup check did not settle; running final recheck before rollback." in log
    assert "Final panel startup recheck: service=active; socket=listening; port=18080; attempts=2" in log
    assert "Health OK: HTTP 200 from http://127.0.0.1:18080/health" in log
    assert "Final panel startup recheck: recovered; service=active; socket=listening; /health=ok; /login=ok" in log


def test_login_never_ready_fails_after_bounded_retries_and_final_recheck(tmp_path: Path) -> None:
    result, log, count = _run_stage(
        tmp_path,
        login_success_after=0,
        primary_attempts=3,
        final_attempts=2,
    )
    assert result.returncode != 0
    assert count == 5
    assert "Login attempt 3/3: service=active; HTTP 000; curl rc=28" in log
    assert "Final panel startup recheck: service=active; socket=listening; port=18080; attempts=2" in log
    assert "Login attempt 2/2: service=active; HTTP 000; curl rc=28" in log
    assert "Final panel startup recheck: /login failed after 2 attempts" in log
    assert "Final panel startup recheck: recovered" not in log


def test_installer_has_no_one_shot_login_checks_left() -> None:
    assert 'curl -fsS --max-time 8 "http://127.0.0.1:${BACKEND_PORT}/login"' not in INSTALL
    assert 'curl -fsS --max-time 8 "http://127.0.0.1:${PANEL_PORT}/login"' not in INSTALL
    assert 'panel_startup_verify "http://127.0.0.1:${BACKEND_PORT}" "$BACKEND_PORT" 20' in INSTALL
    assert 'panel_startup_verify "http://127.0.0.1:${PANEL_PORT}" "$PANEL_PORT" 15' in INSTALL
    assert "SG_GATEWAY_02206_PANEL_STARTUP_RETRY_FIX1" in INSTALL
    assert "curl rc=%s" in _function("http_wait_login")
    assert "Final panel startup recheck" in _function("panel_startup_final_recheck")
