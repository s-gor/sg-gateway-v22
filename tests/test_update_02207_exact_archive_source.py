from pathlib import Path
import subprocess


ROOT = Path(__file__).parents[1]
CORE = ROOT / "deploy" / "update-from-github-core.sh"
WRAPPER = ROOT / "deploy" / "update-from-github-02207.sh"


def test_forced_archive_source_never_attempts_light_git(tmp_path):
    trace = tmp_path / "trace"
    dest = tmp_path / "dest"
    work = tmp_path / "work"
    work.mkdir()

    script = f'''set -Eeuo pipefail
export SG_GATEWAY_UPDATE_CORE_LIBRARY_ONLY=1
export SG_GATEWAY_UPDATE_SOURCE_MODE=archive
source {CORE!s}
prepare_source_light() {{ printf '%s\\n' LIGHT >> {trace!s}; return 97; }}
prepare_source_archive() {{
  mkdir -p {dest!s}
  printf '%s\\n' ARCHIVE >> {trace!s}
  printf '%s\\n' 0.1.0 > {dest!s}/VERSION
  return 0
}}
prepare_source {dest!s} 5193bde751b14effba04450b4dc4619c67fd4162 {work!s}
cat {trace!s}
'''
    completed = subprocess.run(
        ["bash", "-c", script],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.splitlines() == ["ARCHIVE"]
    assert "LIGHT source failed" not in completed.stderr


def test_02207_bootstraps_exact_commit_core_and_forces_archive_source():
    wrapper = WRAPPER.read_text(encoding="utf-8")

    assert (
        "https://raw.githubusercontent.com/${REPOSITORY}/${REQUESTED_SOURCE_COMMIT}/"
        "deploy/update-from-github-core.sh"
    ) in wrapper
    assert "SG_GATEWAY_UPDATE_SOURCE_MODE=archive" in wrapper
    assert 'bash "$PREFIX/deploy/update-from-github.sh"' not in wrapper
    assert "SG_GATEWAY_UPDATE_CORE_LIBRARY_ONLY=1" in wrapper
