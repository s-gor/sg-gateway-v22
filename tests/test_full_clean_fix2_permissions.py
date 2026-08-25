from __future__ import annotations

import os
import pwd
import shutil
import stat
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
INSTALLER = (ROOT / "install.sh").read_text(encoding="utf-8")


def test_main_resets_inherited_umask_before_creating_files() -> None:
    start = INSTALLER.index("main() {")
    block = INSTALLER[start : start + 700]
    assert "  require_root\n" in block
    assert "  umask 022\n  prepare_log\n" in block


def test_resume_secret_umask_is_scoped() -> None:
    start = INSTALLER.index("save_resume_state() {")
    end = INSTALLER.index("\n}\n\nload_resume_state()", start)
    block = INSTALLER[start:end]
    assert "  (\n    umask 077\n" in block
    assert "    chmod 0600 \"$RESUME_FILE\"\n  )" in block


def test_source_and_venv_are_normalized_for_service_user() -> None:
    assert 'chmod -R a+rX "$PREFIX"' in INSTALLER
    assert 'chmod -R go-w "$PREFIX"' in INSTALLER
    assert 'chmod 0755 "$PREFIX"' in INSTALLER
    assert 'chmod -R a+rX "$PREFIX/.venv"' in INSTALLER
    assert 'runuser -u "$PANEL_USER" -- test -x "$PREFIX/.venv/bin/python"' in INSTALLER
    assert 'Application imports as service user: OK' in INSTALLER
    assert 'runuser -u "$PANEL_USER" -- test -r "$PREFIX/app/main.py"' in INSTALLER


def test_restrictive_parent_and_venv_are_repaired_for_unprivileged_execution(tmp_path: Path) -> None:
    app_root = tmp_path / "opt" / "sg-gateway"
    app_root.mkdir(parents=True)
    app_file = app_root / "main.py"
    app_file.write_text("VALUE = 1\n", encoding="utf-8")
    venv = app_root / ".venv"
    subprocess.run(["bash", "-lc", f"umask 077; python3 -m venv {venv!s}"], check=True)

    subprocess.run(["chmod", "-R", "a+rX", str(app_root)], check=True)
    subprocess.run(["chmod", "-R", "go-w", str(app_root)], check=True)
    subprocess.run(["chmod", "0755", str(app_root)], check=True)

    for path in (app_root, venv, venv / "bin"):
        mode = stat.S_IMODE(path.stat().st_mode)
        assert mode & stat.S_IXOTH, (path, oct(mode))
    assert os.access(venv / "bin" / "python", os.X_OK)
    assert app_file.stat().st_mode & stat.S_IROTH

    runuser = shutil.which("runuser")
    if os.geteuid() == 0 and runuser:
        nobody = pwd.getpwnam("nobody")
        current = tmp_path
        while current != current.parent and current != Path("/tmp"):
            current.chmod(current.stat().st_mode | stat.S_IXOTH | stat.S_IROTH)
            current = current.parent
        result = subprocess.run(
            [runuser, "-u", nobody.pw_name, "--", str(venv / "bin" / "python"), "-c", f"exec(open({str(app_file)!r}).read()); print(VALUE)"],
            text=True,
            capture_output=True,
            check=False,
        )
        if "cannot set groups: Operation not permitted" in result.stderr:
            pytest.skip("container lacks CAP_SETGID for runuser validation")
        assert result.returncode == 0, result.stdout + result.stderr
        assert result.stdout.strip() == "1"
