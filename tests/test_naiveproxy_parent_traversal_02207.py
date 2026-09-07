from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).parents[1]
INSTALLER = ROOT / "deploy/install-naiveproxy.sh"


def _shell_function(source: str, name: str) -> str:
    match = re.search(rf"(?ms)^{re.escape(name)}\(\) \{{\n.*?^\}}$", source)
    assert match is not None, f"shell function is missing: {name}"
    return match.group(0)


def test_naive_installer_grants_only_parent_directory_traversal() -> None:
    source = INSTALLER.read_text(encoding="utf-8")

    assert 'PANEL_CONFIG_DIR="/etc/sg-gateway"' in source
    assert 'PANEL_CONFIG_MODE="$(stat -c \'%a\' "$PANEL_CONFIG_DIR")"' in source
    assert 'chmod o+x "$PANEL_CONFIG_DIR"' in source

    assert 'install -d -o root -g sg-naiveproxy -m 0750 "$CONFIG_DIR"' in source
    assert 'chmod 0640 "$CONFIG_DIR/Caddyfile"' in source


def test_naive_installer_restores_parent_mode_on_rollback() -> None:
    source = INSTALLER.read_text(encoding="utf-8")
    rollback = _shell_function(source, "rollback_install")

    assert 'chmod "$PANEL_CONFIG_MODE" "$PANEL_CONFIG_DIR"' in rollback


def test_naive_installer_does_not_broaden_parent_or_panel_group_membership() -> None:
    source = INSTALLER.read_text(encoding="utf-8")

    assert 'chmod 0755 "$PANEL_CONFIG_DIR"' not in source
    assert 'chmod 0775 "$PANEL_CONFIG_DIR"' not in source
    assert not re.search(r"\busermod\b[^\n]*\bsg-gateway\b", source)
    assert not re.search(r"\bgpasswd\b[^\n]*\bsg-gateway\b", source)
