from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INSTALL = ROOT / "install.sh"
UNINSTALL = ROOT / "deploy/full-uninstall-ubuntu.sh"
MATCH = "include /etc/nginx/stream-conf.d/sg-gateway-443.conf;"


def _extract(text: str, pattern: str) -> str:
    match = re.search(pattern, text, re.S | re.M)
    assert match, pattern
    return match.group(1)


def test_rc141_regression_is_deterministic_and_fixed(tmp_path: Path) -> None:
    """Reproduce the old SIGPIPE class deterministically, then prove capture-first is safe."""
    fake_nginx = tmp_path / "nginx"
    fake_nginx.write_text(
        "#!/bin/sh\n"
        f"printf '%s\\n' '{MATCH}'\n"
        # 4 MiB is far larger than a pipe buffer. grep -q exits after line 1,
        # so the producer is guaranteed to still be writing and receives SIGPIPE.
        "dd if=/dev/zero bs=65536 count=64 2>/dev/null | tr '\\000' x\n",
        encoding="utf-8",
    )
    fake_nginx.chmod(0o755)
    env = os.environ.copy()
    env["PATH"] = f"{tmp_path}:{env['PATH']}"

    old = subprocess.run(
        [
            "bash",
            "-c",
            f"set -o pipefail; nginx -T 2>&1 | grep -Fq {MATCH!r}; printf '%s' $?",
        ],
        text=True,
        capture_output=True,
        env=env,
        check=False,
    )
    assert old.stdout == "141", old.stderr + old.stdout

    fixed = subprocess.run(
        [
            "bash",
            "-c",
            f"set -o pipefail; dump=\"$(nginx -T 2>&1)\"; grep -Fq {MATCH!r} <<<\"$dump\"",
        ],
        text=True,
        capture_output=True,
        env=env,
        check=False,
    )
    assert fixed.returncode == 0, fixed.stderr + fixed.stdout


def test_installers_forbid_quiet_grep_after_pipe() -> None:
    """Prevent the producer|grep -q construction from returning to safety-critical scripts."""
    dangerous = re.compile(r"\|[^\n]*\bgrep\b[^\n]*-[A-Za-z]*q")
    for path in (INSTALL, UNINSTALL):
        text = path.read_text(encoding="utf-8")
        assert not dangerous.search(text), f"dangerous producer | grep -q returned in {path}"


def test_clean_install_late_failure_restores_package_nginx_baseline(tmp_path: Path) -> None:
    """Nginx absent -> package config appears -> SG edits -> rollback -> package config survives."""
    text = INSTALL.read_text(encoding="utf-8")
    array = _extract(text, r"(MANAGED_PATHS=\(.*?^\))")
    function = _extract(text, r"(rollback_remove_managed_paths\(\) \{.*?^\})\n\nrestore_backup\(\)")

    root = tmp_path / "root"
    nginx_conf = root / "etc/nginx/nginx.conf"
    sg_stream = root / "etc/nginx/stream-conf.d/sg-gateway-443.conf"
    nginx_conf.parent.mkdir(parents=True)
    sg_stream.parent.mkdir(parents=True)

    # Before installation Nginx was absent. apt creates a healthy package config.
    package_config = "events {}\nhttp {}\n"
    nginx_conf.write_text(package_config, encoding="utf-8")

    baseline = tmp_path / "nginx-after-packages.tar"
    subprocess.run(
        ["tar", "-C", str(root), "-cpf", str(baseline), "etc/nginx"],
        check=True,
        capture_output=True,
        text=True,
    )

    # SG-Gateway then edits Nginx and creates owned stream config.
    nginx_conf.write_text(package_config + "stream { include /etc/nginx/stream-conf.d/sg-gateway-443.conf; }\n", encoding="utf-8")
    sg_stream.write_text("map $ssl_preread_server_name $backend {}\n", encoding="utf-8")

    harness = f"""set -Eeuo pipefail
{array}
{function}
rollback_remove_managed_paths {str(root)!r}
"""
    result = subprocess.run(["bash", "-c", harness], text=True, capture_output=True)
    assert result.returncode == 0, result.stderr + result.stdout

    # Generic rollback must remove SG-owned files but must never blindly delete nginx.conf.
    assert nginx_conf.exists()
    assert not sg_stream.exists()

    # Exact package baseline then overwrites SG's nginx.conf edit.
    subprocess.run(
        ["tar", "-C", str(root), "-xpf", str(baseline)],
        check=True,
        capture_output=True,
        text=True,
    )
    assert nginx_conf.read_text(encoding="utf-8") == package_config


def test_apt_failure_before_nginx_snapshot_does_not_delete_package_config(tmp_path: Path) -> None:
    """If apt fails after creating nginx.conf but before snapshot, rollback still preserves it."""
    text = INSTALL.read_text(encoding="utf-8")
    array = _extract(text, r"(MANAGED_PATHS=\(.*?^\))")
    function = _extract(text, r"(rollback_remove_managed_paths\(\) \{.*?^\})\n\nrestore_backup\(\)")

    root = tmp_path / "root"
    nginx_conf = root / "etc/nginx/nginx.conf"
    nginx_conf.parent.mkdir(parents=True)
    nginx_conf.write_text("package-created-before-apt-error\n", encoding="utf-8")

    result = subprocess.run(
        ["bash", "-c", f"set -Eeuo pipefail\n{array}\n{function}\nrollback_remove_managed_paths {str(root)!r}\n"],
        text=True,
        capture_output=True,
    )
    assert result.returncode == 0, result.stderr + result.stdout
    assert nginx_conf.read_text(encoding="utf-8") == "package-created-before-apt-error\n"


def test_uninstall_partial_install_skips_nginx_test_when_config_missing(tmp_path: Path) -> None:
    """nginx binary exists + nginx.conf missing must not make uninstall fail."""
    text = UNINSTALL.read_text(encoding="utf-8")
    function = _extract(
        text,
        r"(check_nginx_after_sg_cleanup\(\) \{.*?^\})\n\nremove_service_and_web_config_finalize_nginx\(\)",
    )

    bindir = tmp_path / "bin"
    bindir.mkdir()
    marker = tmp_path / "nginx-was-called"
    fake_nginx = bindir / "nginx"
    fake_nginx.write_text(
        f"#!/bin/sh\nprintf called > {str(marker)!r}\nexit 91\n",
        encoding="utf-8",
    )
    fake_nginx.chmod(0o755)
    missing = tmp_path / "missing-nginx.conf"
    env = os.environ.copy()
    env["PATH"] = f"{bindir}:{env['PATH']}"

    result = subprocess.run(
        ["bash", "-c", f"set -Eeuo pipefail\n{function}\ncheck_nginx_after_sg_cleanup {str(missing)!r}\n"],
        text=True,
        capture_output=True,
        env=env,
    )
    assert result.returncode == 0, result.stderr + result.stdout
    assert "nginx -t пропущен" in result.stdout
    assert not marker.exists(), "nginx -t was called even though nginx.conf was missing"
