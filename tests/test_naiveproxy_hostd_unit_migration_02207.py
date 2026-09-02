import os
import re
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).parents[1]


def _shell_function(source: str, name: str) -> str:
    match = re.search(
        rf"(?ms)^{re.escape(name)}\(\) \{{\n.*?^\}}$",
        source,
    )
    assert match is not None, f"shell function is missing: {name}"
    return match.group(0)


def test_runtime_installer_installs_naiveproxy_capable_hostd_unit():
    source = (ROOT / "deploy/install-naiveproxy.sh").read_text()
    assert 'HOSTD_SERVICE="sg-hostd.service"' in source
    assert 'HOSTD_SERVICE_PATH="/etc/systemd/system/$HOSTD_SERVICE"' in source
    assert '"$SOURCE_ROOT/hostd/systemd/$HOSTD_SERVICE"' in source
    assert 'install -m 0644 "$SOURCE_ROOT/hostd/systemd/$HOSTD_SERVICE" "$HOSTD_SERVICE_PATH"' in source
    assert 'systemctl restart "$HOSTD_SERVICE"' in source
    assert 'systemctl is-active --quiet "$HOSTD_SERVICE"' in source


def test_runtime_installer_rolls_back_hostd_unit_and_state():
    source = (ROOT / "deploy/install-naiveproxy.sh").read_text()
    assert 'snapshot_path "$HOSTD_SERVICE_PATH" hostd-unit HAD_HOSTD_UNIT' in source
    assert 'restore_path "$HOSTD_SERVICE_PATH" hostd-unit "$HAD_HOSTD_UNIT"' in source
    assert 'HOSTD_WAS_ACTIVE' in source
    assert 'HOSTD_WAS_ENABLED' in source
    assert 'restore_service_state "$HOSTD_SERVICE" "$HOSTD_WAS_ENABLED" "$HOSTD_WAS_ACTIVE"' in source


def test_stable_hostd_sandbox_requires_02207_unit_migration():
    unit = (ROOT / "hostd/systemd/sg-hostd.service").read_text()
    assert "-/etc/sg-gateway/naiveproxy" in unit
    assert "-/var/lib/sg-gateway" in unit


def test_hostd_service_imports_with_unit_pythonpath():
    unit = (ROOT / "hostd/systemd/sg-hostd.service").read_text()
    match = re.search(r"^Environment=PYTHONPATH=(.+)$", unit, re.MULTILINE)
    assert match, "sg-hostd.service must declare PYTHONPATH"

    configured = match.group(1).strip().strip('"')
    assert "/opt/sg-gateway" in configured.split(":")
    assert "/opt/sg-gateway/hostd" in configured.split(":")

    local_pythonpath = configured.replace("/opt/sg-gateway", str(ROOT))
    env = os.environ.copy()
    env["PYTHONPATH"] = local_pythonpath
    result = subprocess.run(
        [sys.executable, "-c", "import sg_hostd.app"],
        cwd=ROOT / "hostd",
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def test_panel_update_installs_02207_hostd_unit_before_first_restart():
    core = (ROOT / "deploy/update-from-github-core.sh").read_text()
    prepare_light = _shell_function(core, "prepare_source_light")
    deploy = _shell_function(core, "deploy_source")
    main = _shell_function(core, "main")

    assert "/hostd/systemd/sg-hostd.service" in prepare_light
    assert '[[ -f "$PREFIX/hostd/systemd/sg-hostd.service" ]]' in deploy
    assert 'install -m 0644 "$PREFIX/hostd/systemd/sg-hostd.service" "$HOSTD_UNIT"' in deploy
    assert deploy.index('install -m 0644 "$PREFIX/hostd/systemd/sg-hostd.service" "$HOSTD_UNIT"') < deploy.index("systemctl daemon-reload")
    assert main.index('run_stage 3 "Обновление исходников SG-Gateway + WSGI migration" deploy_source') < main.index('run_stage 5 "Перезапуск только panel + hostd" restart_panel')
