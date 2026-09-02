from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).parents[1]
INSTALLER = ROOT / "install.sh"
NAIVE_INSTALLER = ROOT / "deploy/install-naiveproxy.sh"
HOSTD_UNIT = ROOT / "hostd/systemd/sg-hostd.service"
WRAPPER = ROOT / "deploy/update-from-github-02207.sh"

_REQUIRED_ENV_FILES = (
    "EnvironmentFile=/etc/sg-gateway/sg-gateway.env",
    "EnvironmentFile=/etc/sg-gateway/runtime.env",
    "EnvironmentFile=/etc/sg-gateway/engine-secrets.env",
)


def _shell_function(source: str, name: str) -> str:
    match = re.search(rf"(?ms)^{re.escape(name)}\(\) \{{\n.*?^\}}$", source)
    assert match is not None, f"shell function is missing: {name}"
    return match.group(0)


def test_clean_install_final_hostd_unit_preserves_shared_environment_contract():
    installer = INSTALLER.read_text(encoding="utf-8")
    naive = NAIVE_INSTALLER.read_text(encoding="utf-8")
    unit = HOSTD_UNIT.read_text(encoding="utf-8")

    assert "SG_GATEWAY_OPERATION_JOB_DIR=${DATA_DIR}/security/jobs" in installer
    assert (
        'install -m 0644 "$SOURCE_ROOT/hostd/systemd/$HOSTD_SERVICE" '
        '"$HOSTD_SERVICE_PATH"'
    ) in naive

    for line in _REQUIRED_ENV_FILES:
        assert line in unit


def test_02207_wrapper_rejects_hostd_unit_that_drops_environment_files():
    source = WRAPPER.read_text(encoding="utf-8")
    preflight = _shell_function(source, "prepare_hostd_preflight_bridge")
    staged = _shell_function(source, "stage_naive_hostd_unit")

    for line in _REQUIRED_ENV_FILES:
        assert line in preflight
        assert line in staged
