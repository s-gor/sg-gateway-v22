from __future__ import annotations

import os
import subprocess
from pathlib import Path

# Avoid the accepted stage-2 import hook being entered through a partial
# app.mihomo.service import in the global test isolation fixture.
from app.clients import repository as _repository  # noqa: F401


ROOT = Path(__file__).resolve().parents[1]
WRAPPER = ROOT / "deploy/update-from-github.sh"
SHA = "a" * 40


def _toolbox(tmp_path: Path, *, with_git: bool) -> tuple[Path, Path]:
    bindir = tmp_path / "bin"
    bindir.mkdir()
    for name in ("bash", "python3", "mktemp", "rm", "head", "grep", "awk", "cp"):
        target = Path("/usr/bin") / name
        if not target.exists():
            target = Path("/bin") / name
        (bindir / name).symlink_to(target)
    log = tmp_path / "requests.log"
    curl = bindir / "curl"
    curl.write_text(
        """#!/usr/bin/env bash
set -euo pipefail
url=""
output=""
while (($#)); do
  case "$1" in
    -o) output=$2; shift 2 ;;
    -*) shift ;;
    *) url=$1; shift ;;
  esac
done
printf '%s\n' "$url" >> "$REQUEST_LOG"
if [[ $url == *api.github.com* ]]; then
  printf '{"sha":"%s"}\n' "$API_SHA"
elif [[ -n $output ]]; then
  cp "$CORE_PAYLOAD" "$output"
else
  exit 64
fi
"""
    )
    curl.chmod(0o755)
    if with_git:
        git = bindir / "git"
        git.write_text(
            """#!/usr/bin/env bash
printf '%s\trefs/heads/%s\n' "$GIT_SHA" "$SG_GATEWAY_GITHUB_BRANCH"
"""
        )
        git.chmod(0o755)
    return bindir, log


def _core(tmp_path: Path, *, exit_code: int = 0, valid: bool = True) -> Path:
    path = tmp_path / "core.sh"
    if valid:
        path.write_text(
            "#!/usr/bin/env bash\n# SG_GATEWAY_UPDATE_CORE\n"
            "printf '%s' \"$SG_GATEWAY_SOURCE_COMMIT\" > \"$CORE_RESULT\"\n"
            f"exit {exit_code}\n"
        )
    else:
        path.write_text("<html>not a shell script</html>\n")
    return path


def _run(
    tmp_path: Path,
    *,
    with_git: bool,
    core: Path,
    branch: str = "feature/awg31-independent-profile",
) -> tuple[subprocess.CompletedProcess[str], Path, Path]:
    bindir, log = _toolbox(tmp_path, with_git=with_git)
    result_file = tmp_path / "core-result"
    bootstrap_tmp = tmp_path / "tmp"
    bootstrap_tmp.mkdir()
    env = {
        "PATH": str(bindir),
        "TMPDIR": str(bootstrap_tmp),
        "REQUEST_LOG": str(log),
        "CORE_PAYLOAD": str(core),
        "CORE_RESULT": str(result_file),
        "API_SHA": SHA,
        "GIT_SHA": SHA,
        "SG_GATEWAY_GITHUB_BRANCH": branch,
        "SG_GATEWAY_GIT_URL": "https://example.invalid/repository.git",
        "SG_GATEWAY_RAW_BASE_URL": "https://raw.example.invalid/repository",
    }
    completed = subprocess.run(
        ["/bin/bash"],
        input=WRAPPER.read_text(),
        cwd=tmp_path,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    return completed, result_file, bootstrap_tmp


def test_public_wrapper_runs_from_stdin_without_bash_source_or_repository_cwd(tmp_path: Path) -> None:
    completed, result_file, _ = _run(tmp_path, with_git=True, core=_core(tmp_path))

    assert completed.returncode == 0, completed.stderr
    assert result_file.read_text() == SHA
    assert f"Bootstrap commit: {SHA}" in completed.stdout


def test_wrapper_url_encodes_feature_ref_and_works_without_git(tmp_path: Path) -> None:
    completed, result_file, _ = _run(tmp_path, with_git=False, core=_core(tmp_path))

    assert completed.returncode == 0, completed.stderr
    assert result_file.read_text() == SHA
    requests = (tmp_path / "requests.log").read_text().splitlines()
    assert any("feature%2Fawg31-independent-profile" in request for request in requests)


def test_wrapper_downloads_core_from_the_exact_resolved_commit(tmp_path: Path) -> None:
    completed, _, _ = _run(tmp_path, with_git=True, core=_core(tmp_path))

    assert completed.returncode == 0, completed.stderr
    requests = (tmp_path / "requests.log").read_text().splitlines()
    assert requests == [f"https://raw.example.invalid/repository/{SHA}/deploy/update-from-github-core.sh"]


def test_wrapper_rejects_non_core_download_before_execution(tmp_path: Path) -> None:
    completed, result_file, _ = _run(
        tmp_path, with_git=True, core=_core(tmp_path, valid=False)
    )

    assert completed.returncode != 0
    assert not result_file.exists()
    assert "downloaded core updater" in completed.stderr


def test_wrapper_preserves_core_exit_code_and_removes_bootstrap_directory(tmp_path: Path) -> None:
    completed, result_file, bootstrap_tmp = _run(
        tmp_path, with_git=True, core=_core(tmp_path, exit_code=37)
    )

    assert completed.returncode == 37
    assert result_file.read_text() == SHA
    assert list(bootstrap_tmp.iterdir()) == []
