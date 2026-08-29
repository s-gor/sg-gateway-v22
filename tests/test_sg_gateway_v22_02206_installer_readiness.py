from __future__ import annotations

import os
import re
import shlex
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INSTALL = (ROOT / "deploy/install-core.sh").read_text(encoding="utf-8")
WORKFLOW = (ROOT / ".github" / "workflows" / "dev-02206-guard.yml").read_text(encoding="utf-8")


def _function(name: str) -> str:
    match = re.search(rf"(?ms)^{re.escape(name)}\(\) \{{\n.*?^\}}\n", INSTALL)
    assert match, name
    return match.group(0)


def _fake_runtime(tmp_path: Path) -> tuple[Path, Path, Path]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    state = tmp_path / "curl-count"
    log = tmp_path / "installer.log"
    (bin_dir / "curl").write_text(
        r'''#!/usr/bin/env bash
set -u
out=""
url=""
while (($#)); do
  case "$1" in
    -o) out="$2"; shift 2 ;;
    -w) shift 2 ;;
    --max-time|--connect-timeout|--resolve|--noproxy) shift 2 ;;
    -sS|-ksS|-fsS|-kfsS|-k|-f) shift ;;
    *) url="$1"; shift ;;
  esac
done
count=0
[[ ! -f "$SG_TEST_STATE" ]] || count="$(cat "$SG_TEST_STATE")"
count=$((count + 1))
printf '%s' "$count" > "$SG_TEST_STATE"
success_after="${SG_TEST_SUCCESS_AFTER:-0}"
if (( success_after <= 0 || count < success_after )); then
  printf '000'
  exit 28
fi
case "${SG_TEST_KIND:-}" in
  commands)
    printf '%s' '{"commands":["clients.apply","tls.issue.start","xray.apply","xray.apply.start","xray.test","xray.rollback","warp.install","warp.test","warp.export_json"]}' > "$out"
    ;;
  health)
    printf '%s' '{"service":"sg-gateway-panel","status":"ok"}' > "$out"
    ;;
  placeholder)
    printf '%s' 'SG placeholder' > "$out"
    ;;
  *) exit 90 ;;
esac
printf '200'
''',
        encoding="utf-8",
    )
    (bin_dir / "sleep").write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
    for path in bin_dir.iterdir():
        os.chmod(path, 0o755)
    return bin_dir, state, log


def _run_waiter(
    tmp_path: Path,
    *,
    function_name: str,
    call: str,
    kind: str,
    success_after: int,
) -> tuple[subprocess.CompletedProcess[str], str, int]:
    bin_dir, state, log = _fake_runtime(tmp_path)
    script = f"""set -Eeuo pipefail
INSTALL_LOG={shlex.quote(str(log))}
{_function(function_name)}
{call}
"""
    env = os.environ.copy()
    env["PATH"] = f"{bin_dir}:{env['PATH']}"
    env["SG_TEST_STATE"] = str(state)
    env["SG_TEST_KIND"] = kind
    env["SG_TEST_SUCCESS_AFTER"] = str(success_after)
    env["SG_GATEWAY_STARTUP_RETRY_DELAY"] = "0"
    env["SG_GATEWAY_STARTUP_REQUEST_TIMEOUT"] = "1"
    result = subprocess.run(
        ["bash", "-c", script], env=env, text=True, capture_output=True, check=False
    )
    body = log.read_text(encoding="utf-8") if log.exists() else ""
    count = int(state.read_text(encoding="utf-8")) if state.exists() else 0
    return result, body, count


def test_hostd_commands_timeout_then_valid_contract_recovers(tmp_path: Path) -> None:
    result, log, count = _run_waiter(
        tmp_path,
        function_name="http_wait_hostd_commands",
        call='http_wait_hostd_commands "http://127.0.0.1:8090/commands" 5',
        kind="commands",
        success_after=3,
    )
    assert result.returncode == 0, result.stderr
    assert count == 3
    assert "Hostd commands attempt 1/5: HTTP 000; curl rc=28" in log
    assert "Hostd commands OK: HTTP 200" in log


def test_hostd_commands_never_ready_fails_bounded(tmp_path: Path) -> None:
    result, log, count = _run_waiter(
        tmp_path,
        function_name="http_wait_hostd_commands",
        call='http_wait_hostd_commands "http://127.0.0.1:8090/commands" 3',
        kind="commands",
        success_after=0,
    )
    assert result.returncode != 0
    assert count == 3
    assert "Hostd commands attempt 3/3: HTTP 000; curl rc=28" in log


def test_saved_https_health_timeout_then_ok_recovers(tmp_path: Path) -> None:
    result, log, count = _run_waiter(
        tmp_path,
        function_name="http_wait_resolved_https_json",
        call='http_wait_resolved_https_json "panel.example" 63443 "sg-gateway-panel" 5',
        kind="health",
        success_after=2,
    )
    assert result.returncode == 0, result.stderr
    assert count == 2
    assert "HTTPS health attempt 1/5: HTTP 000; curl rc=28" in log
    assert "HTTPS health OK: HTTP 200" in log


def test_placeholder_timeout_then_exact_body_recovers(tmp_path: Path) -> None:
    expected = tmp_path / "placeholder.html"
    expected.write_text("SG placeholder", encoding="utf-8")
    result, log, count = _run_waiter(
        tmp_path,
        function_name="http_wait_file_match",
        call=f'http_wait_file_match "http://127.0.0.1/" {shlex.quote(str(expected))} 5',
        kind="placeholder",
        success_after=2,
    )
    assert result.returncode == 0, result.stderr
    assert count == 2
    assert "HTTP body attempt 1/5: HTTP 000; curl rc=28" in log
    assert "HTTP body OK: HTTP 200" in log


def test_startup_verifiers_do_not_use_the_old_one_shot_curls() -> None:
    hostd = _function("stage9_verify_hostd")
    nginx = _function("stage9_verify_nginx")
    assert "http_wait_hostd_commands" in hostd
    assert "curl -fsS --max-time 8" not in hostd
    assert "http_wait_resolved_https_json" in nginx
    assert "http_wait_file_match" in nginx
    assert "curl --noproxy '*' -kfsS --max-time 15" not in nginx
    assert "curl --noproxy '*' -fsS --max-time 8 http://127.0.0.1/" not in nginx


def test_guard_runs_02206_startup_regressions_explicitly() -> None:
    assert "tests/test_sg_gateway_v22_02206_panel_startup_retry.py" in WORKFLOW
    assert "tests/test_sg_gateway_v22_02206_installer_readiness.py" in WORKFLOW
