from pathlib import Path
import os
import subprocess


ROOT = Path(__file__).resolve().parents[1]
INSTALLER = ROOT / "deploy" / "install-naiveproxy.sh"


def _installer_source() -> str:
    return INSTALLER.read_text(encoding="utf-8")


def _download_function() -> str:
    source = _installer_source()
    start = source.index("download_runtime_archive() {")
    end = source.index("\n}\n", start) + len("\n}\n")
    return source[start:end]


def _write_fake_tools(tmp_path: Path, mode: str) -> tuple[Path, Path]:
    attempts = tmp_path / "curl-attempts"
    fake_curl = tmp_path / "curl"
    fake_curl.write_text(
        "#!/usr/bin/env bash\n"
        "set -uo pipefail\n"
        "out=''\n"
        "while (($#)); do\n"
        "  case \"$1\" in\n"
        "    -o) out=\"$2\"; shift 2 ;;\n"
        "    *) shift ;;\n"
        "  esac\n"
        "done\n"
        "[[ -n \"$out\" ]] || exit 97\n"
        "count=0\n"
        "[[ ! -f \"$SG_TEST_ATTEMPTS\" ]] || count=$(cat \"$SG_TEST_ATTEMPTS\")\n"
        "count=$((count + 1))\n"
        "printf '%s\\n' \"$count\" > \"$SG_TEST_ATTEMPTS\"\n"
        "printf 'partial-attempt-%s' \"$count\" > \"$out\"\n"
        "if [[ \"$SG_TEST_MODE\" == transient && \"$count\" -ge 2 ]]; then\n"
        "  printf 'complete-runtime' > \"$out\"\n"
        "  exit 0\n"
        "fi\n"
        "exit 56\n",
        encoding="utf-8",
    )
    fake_curl.chmod(0o755)

    fake_sleep = tmp_path / "sleep"
    fake_sleep.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
    fake_sleep.chmod(0o755)
    return attempts, fake_curl


def _run_download(tmp_path: Path, mode: str, attempts_count: int) -> subprocess.CompletedProcess[str]:
    attempts, _fake_curl = _write_fake_tools(tmp_path, mode)
    destination = tmp_path / "runtime.tar.xz"
    script = f"""
set -uo pipefail
{_download_function()}
PATH={tmp_path}:/usr/bin:/bin
export SG_TEST_ATTEMPTS={attempts}
export SG_TEST_MODE={mode}
download_runtime_archive https://example.invalid/runtime {destination} {attempts_count}
"""
    result = subprocess.run(
        ["bash", "-c", script],
        capture_output=True,
        text=True,
        check=False,
        env={**os.environ},
    )
    result.destination = destination  # type: ignore[attr-defined]
    result.attempts_file = attempts  # type: ignore[attr-defined]
    return result


def test_naiveproxy_download_retries_rc56_and_promotes_only_complete_file(tmp_path: Path) -> None:
    result = _run_download(tmp_path, "transient", 3)
    destination = result.destination  # type: ignore[attr-defined]
    attempts = result.attempts_file  # type: ignore[attr-defined]

    assert result.returncode == 0, result.stderr
    assert attempts.read_text(encoding="utf-8").strip() == "2"
    assert destination.read_text(encoding="utf-8") == "complete-runtime"
    assert not Path(str(destination) + ".part").exists()


def test_naiveproxy_download_preserves_last_curl_rc_and_removes_partial_file(tmp_path: Path) -> None:
    result = _run_download(tmp_path, "always-fail", 3)
    destination = result.destination  # type: ignore[attr-defined]
    attempts = result.attempts_file  # type: ignore[attr-defined]

    assert result.returncode == 56
    assert attempts.read_text(encoding="utf-8").strip() == "3"
    assert not destination.exists()
    assert not Path(str(destination) + ".part").exists()
