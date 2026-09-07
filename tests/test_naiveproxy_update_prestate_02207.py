from pathlib import Path
import re
import subprocess


ROOT = Path(__file__).resolve().parents[1]
UPDATE_WRAPPER = ROOT / "deploy" / "update-from-github-02207.sh"


def _shell_function(name: str) -> str:
    body = UPDATE_WRAPPER.read_text(encoding="utf-8")
    match = re.search(
        rf"(?ms)^{re.escape(name)}\(\) \{{\n.*?^\}}$",
        body,
    )
    assert match is not None, f"shell function is missing: {name}"
    return match.group(0)


def test_capture_prestate_succeeds_when_naiveproxy_is_not_installed() -> None:
    function = _shell_function("capture_naive_prestate")
    probe = f"""
set -Eeuo pipefail
TX_DIR=""
NAIVE_UNIT="/definitely-missing/sg-gateway-naiveproxy.service"
NAIVE_SERVICE="sg-gateway-naiveproxy.service"
NAIVE_UNIT_EXISTED=0
NAIVE_USER_EXISTED=0
NAIVE_GROUP_EXISTED=0
NAIVE_WAS_ACTIVE=0
NAIVE_WAS_ENABLED=0

mktemp() {{ printf '/tmp/sg-gateway-02207-prestate-test'; }}
id() {{ return 1; }}
getent() {{ return 2; }}
systemctl() {{ return 3; }}

{function}

capture_naive_prestate
printf 'continued:%s:%s:%s:%s\n' \
  "$NAIVE_USER_EXISTED" "$NAIVE_GROUP_EXISTED" \
  "$NAIVE_WAS_ACTIVE" "$NAIVE_WAS_ENABLED"
"""
    result = subprocess.run(
        ["bash", "-c", probe],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout == "continued:0:0:0:0\n"
