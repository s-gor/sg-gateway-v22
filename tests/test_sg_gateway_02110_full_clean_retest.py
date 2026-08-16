from __future__ import annotations

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _clean_nginx(text: str) -> str:
    text = re.sub(
        r"(?ms)\n*# SG_GATEWAY_PLACEHOLDER_80_443_V3\s*\nstream\s*\{\s*"
        r"include\s+/etc/nginx/stream-conf\.d/(?:sg-gateway-443\.conf|\*\.conf);\s*\}\s*",
        "\n",
        text,
        count=1,
    )
    text = re.sub(
        r"(?m)^\s*include\s+/etc/nginx/stream-conf\.d/sg-gateway-443\.conf;\s*\n?",
        "",
        text,
    )
    text = re.sub(
        r"(?m)^\s*# SG_GATEWAY_PLACEHOLDER_80_443_V3\s*\n?",
        "",
        text,
    )
    return text.rstrip() + "\n"


def test_https_verifier_retries_temporary_404() -> None:
    script = (ROOT / "deploy/configure-panel-access.sh").read_text(encoding="utf-8")
    assert "SG_GATEWAY_02110_HTTPS_VERIFY_RETRY_FIX1" in script
    assert "for attempt in $(seq 1 30)" in script
    assert "https://$domain:$PUBLIC_PORT/health" in script
    assert "HTTP ${code:-000}" in script


def test_uninstall_removes_direct_include_from_owned_block() -> None:
    before = "events {}\n\n# SG_GATEWAY_PLACEHOLDER_80_443_V3\nstream {\n    include /etc/nginx/stream-conf.d/sg-gateway-443.conf;\n}\n"
    after = _clean_nginx(before)
    assert "sg-gateway-443.conf" not in after
    assert "stream {" not in after
    assert "events {}" in after


def test_uninstall_removes_only_direct_include_from_shared_block() -> None:
    before = "stream {\n    include /etc/nginx/stream-conf.d/custom.conf;\n    include /etc/nginx/stream-conf.d/sg-gateway-443.conf;\n}\n"
    after = _clean_nginx(before)
    assert "custom.conf" in after
    assert "sg-gateway-443.conf" not in after
    assert "stream {" in after


def test_uninstall_cleans_02110_resume_file() -> None:
    script = (ROOT / "deploy/full-uninstall-ubuntu.sh").read_text(encoding="utf-8")
    assert "/root/sg-gateway-02110-installer-resume.env" in script
    assert "Остаток после удаления: /root/sg-gateway-02110-installer-resume.env" in script


def test_builder_uses_binary_payload_and_transfer_recheck() -> None:
    script = (ROOT / "build-run.sh").read_text(encoding="utf-8")
    assert "__SG_GATEWAY_BINARY_PAYLOAD_V1__" in script
    assert 'cat "$PAYLOAD" >> "$OUT"' in script
    assert "base64 -d" not in script
    assert "unzip -q \"$TRANSFER_ZIP\"" in script
    assert 'bash "$(basename "$OUT")" --verify-only' in script


def test_stage_one_is_live() -> None:
    script = (ROOT / "install.sh").read_text(encoding="utf-8")
    assert 'if [[ "$number" == "1" ]]; then' in script
    assert 'run_live "$CURRENT_LABEL" "$function_name"' in script
    assert "APT/dpkg всё ещё занят; ожидание:" in script


def test_exact_https_shell_functions_survive_two_404_responses(tmp_path: Path) -> None:
    script = (ROOT / "deploy/configure-panel-access.sh").read_text(encoding="utf-8")
    block = re.search(
        r"(?ms)^# SG_GATEWAY_02110_HTTPS_VERIFY_RETRY_FIX1\n(.*?)^apply_client_runtime\(\)",
        script,
    )
    assert block
    placeholder = tmp_path / "placeholder"
    placeholder.mkdir()
    (placeholder / "index.html").write_text("accepted-page\n", encoding="utf-8")
    stream = tmp_path / "stream.conf"
    stream.write_text(
        "www.bing.com 127.0.0.1:7443;\n"
        "default 127.0.0.1:7444;\n",
        encoding="utf-8",
    )
    counter = tmp_path / "counter"
    harness = f"""set -Eeuo pipefail
PLACEHOLDER_ROOT={str(placeholder)!r}
PUBLIC_PORT=63443
STREAM_CONF={str(stream)!r}
REALITY_SNI=www.bing.com
XRAY_INTERNAL_PORT=7443
PLACEHOLDER_TLS_INTERNAL_PORT=7444
COUNTER={str(counter)!r}
log() {{ printf '%s\\n' \"$*\"; }}
fail() {{ printf 'FAIL: %s\\n' \"$*\" >&2; return 1; }}
sleep() {{ :; }}
systemctl() {{ return 0; }}
curl() {{
  local out='' url='' arg count
  while (($#)); do
    arg=\"$1\"; shift
    case \"$arg\" in
      -o) out=\"$1\"; shift ;;
      http://*|https://*) url=\"$arg\" ;;
    esac
  done
  count=0; [[ ! -f \"$COUNTER\" ]] || count=\"$(cat \"$COUNTER\")\"
  count=$((count+1)); printf '%s' \"$count\" > \"$COUNTER\"
  if [[ \"$url\" == *\":63443/health\" ]]; then
    printf '200'; return 0
  fi
  if (( count <= 2 )); then
    [[ -z \"$out\" || \"$out\" == /dev/null ]] || : > \"$out\"
    printf '404'; return 0
  fi
  [[ -z \"$out\" || \"$out\" == /dev/null ]] || cp \"$PLACEHOLDER_ROOT/index.html\" \"$out\"
  printf '200'
}}
{block.group(1)}
verify_https_contract example.test
"""
    result = subprocess.run(["bash", "-c", harness], text=True, capture_output=True)
    assert result.returncode == 0, result.stderr + result.stdout
    assert "HTTP 80: OK" in result.stdout
    assert "HTTPS 443 fallback: OK" in result.stdout
    assert "Панель HTTPS 63443: OK" in result.stdout


def test_exact_uninstall_python_cleans_owned_and_shared_stream_blocks(tmp_path: Path) -> None:
    script = (ROOT / "deploy/full-uninstall-ubuntu.sh").read_text(encoding="utf-8")
    block = re.search(r"<<'PYNGINXCLEAN'\n(.*?)\nPYNGINXCLEAN", script, re.S)
    assert block
    cases = {
        "owned": (
            "events {}\n\n# SG_GATEWAY_PLACEHOLDER_80_443_V3\nstream {\n"
            "    include /etc/nginx/stream-conf.d/sg-gateway-443.conf;\n}\n",
            False,
        ),
        "shared": (
            "# SG_GATEWAY_PLACEHOLDER_80_443_V3\nstream {\n"
            "    include /etc/nginx/stream-conf.d/custom.conf;\n"
            "    include /etc/nginx/stream-conf.d/sg-gateway-443.conf;\n}\n",
            True,
        ),
    }
    for name, (content, should_preserve_custom) in cases.items():
        target = tmp_path / f"{name}.conf"
        target.write_text(content, encoding="utf-8")
        result = subprocess.run(
            ["python3", "-", str(target)],
            input=block.group(1),
            text=True,
            capture_output=True,
        )
        assert result.returncode == 0, result.stderr
        after = target.read_text(encoding="utf-8")
        assert "sg-gateway-443.conf" not in after
        assert "SG_GATEWAY_PLACEHOLDER_80_443_V3" not in after
        assert ("custom.conf" in after) is should_preserve_custom
