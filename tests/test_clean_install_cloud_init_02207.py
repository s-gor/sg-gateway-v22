from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[1]
INSTALLER = ROOT / "deploy" / "install-from-github-02207.sh"


def _installer_source() -> str:
    return INSTALLER.read_text(encoding="utf-8")


def _wait_for_cloud_init_function() -> str:
    source = _installer_source()
    start = source.index("wait_for_cloud_init() {")
    end = source.index("\n}\n", start) + len("\n}\n")
    return source[start:end]


def _run_wait_for_cloud_init(tmp_path: Path, return_code: int) -> subprocess.CompletedProcess[str]:
    fake_cloud_init = tmp_path / "cloud-init"
    fake_cloud_init.write_text(
        "#!/usr/bin/env bash\n"
        "if [[ \"${1:-}\" == \"status\" && \"${2:-}\" == \"--wait\" ]]; then\n"
        "  echo 'status: done'\n"
        f"  exit {int(return_code)}\n"
        "fi\n"
        "exit 99\n",
        encoding="utf-8",
    )
    fake_cloud_init.chmod(0o755)

    script = f"""
set -uo pipefail
fail() {{
  printf 'FAIL:%s\\n' "$*" >&2
  exit 91
}}
{_wait_for_cloud_init_function()}
PATH={tmp_path}:/usr/bin:/bin
wait_for_cloud_init
"""
    return subprocess.run(
        ["bash", "-c", script],
        capture_output=True,
        text=True,
        check=False,
    )


def test_02207_waits_for_cloud_init_before_downloading_source() -> None:
    source = _installer_source()

    assert "wait_for_cloud_init() {" in source
    invocation = source.index("\nwait_for_cloud_init\n")
    assert source.index('[[ ${EUID:-$(id -u)} -eq 0 ]]') < invocation
    assert invocation < source.index('TMP="$(mktemp -d')
    assert invocation < source.index("curl -fL")


def test_02207_cloud_init_exit_zero_continues(tmp_path: Path) -> None:
    result = _run_wait_for_cloud_init(tmp_path, 0)

    assert result.returncode == 0, result.stderr
    assert "cloud-init: ready" in result.stdout


def test_02207_cloud_init_exit_two_is_recoverable(tmp_path: Path) -> None:
    result = _run_wait_for_cloud_init(tmp_path, 2)

    assert result.returncode == 0, result.stderr
    assert "recoverable" in (result.stdout + result.stderr).lower()
    assert "cloud-init: ready" in result.stdout


def test_02207_cloud_init_exit_one_still_blocks_install(tmp_path: Path) -> None:
    result = _run_wait_for_cloud_init(tmp_path, 1)

    assert result.returncode == 91
    assert "cloud-init did not finish successfully" in result.stderr
