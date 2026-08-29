from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_repair_builds_and_installs_executable_awg31_runtime_in_isolated_prefix(
    tmp_path: Path,
) -> None:
    prefix = tmp_path / "prefix"
    vendor = prefix / "vendor" / "cores"
    deploy = prefix / "deploy"
    vendor.mkdir(parents=True)
    deploy.mkdir(parents=True)

    for filename in (
        "amneziawg-tools-3.1.20260812.tar.gz",
        "amneziawg-go-linux-amd64-v3.1.20260814",
    ):
        shutil.copy2(ROOT / "vendor" / "cores" / filename, vendor / filename)
    shutil.copy2(
        ROOT / "deploy" / "sg-gateway-awg31.service",
        deploy / "sg-gateway-awg31.service",
    )

    runtime = prefix / "awg31"
    env = os.environ.copy()
    env.update(
        {
            "SG_GATEWAY_PREFIX": str(prefix),
            "SG_GATEWAY_AWG31_RUNTIME": str(runtime),
            "SG_GATEWAY_AWG31_CONFIG_ROOT": str(prefix / "etc/amnezia/amneziawg/awg31"),
            "SG_GATEWAY_AWG31_STATE_ROOT": str(prefix / "var/lib/sg-gateway/awg31"),
            "SG_GATEWAY_SYSTEMD_DIR": str(prefix / "etc/systemd/system"),
            "SG_GATEWAY_SKIP_SYSTEMCTL": "1",
        }
    )

    completed = subprocess.run(
        ["bash", str(ROOT / "deploy/repair-awg31-runtime.sh")],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr

    for filename in ("awg", "awg-quick", "amneziawg-go"):
        executable = runtime / "bin" / filename
        assert executable.is_file(), filename
        assert os.access(executable, os.X_OK), filename

    version = subprocess.run(
        [str(runtime / "bin/awg"), "--version"],
        text=True,
        capture_output=True,
        check=True,
    )
    assert "amnezia" in version.stdout.lower() or "wireguard" in version.stdout.lower()
