from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INSTALL = (ROOT / "install.sh").read_text(encoding="utf-8")
BOOTSTRAP = (ROOT / "deploy" / "install-from-github.sh").read_text(encoding="utf-8")


def _function(source: str, name: str) -> str:
    match = re.search(rf"(?ms)^{re.escape(name)}\(\) \{{\n.*?^\}}\n", source)
    assert match, f"missing installer function: {name}"
    return match.group(0)


def _installed_tree(tmp_path: Path) -> Path:
    prefix = tmp_path / "opt" / "sg-gateway"
    for relative in (
        "app/web/templates/connections.html",
        "app/web/templates/_mihomo_panel.html",
        "app/web/static/sg-xray-profiles-v2.css",
    ):
        source = ROOT / relative
        target = prefix / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    return prefix


def _run_ui_verifier(prefix: Path) -> subprocess.CompletedProcess[str]:
    verifier = _function(INSTALL, "verify_installed_connections_ui_contract")
    script = f"""set -Eeuo pipefail
fail() {{ printf '%s\n' "$*" >&2; return 1; }}
PREFIX={prefix!s}
{verifier}
verify_installed_connections_ui_contract "$PREFIX"
"""
    return subprocess.run(
        ["bash", "-c", script],
        text=True,
        capture_output=True,
        check=False,
        env=os.environ.copy(),
    )


def test_clean_install_bootstrap_can_download_one_exact_source_commit() -> None:
    assert 'SOURCE_COMMIT="${SG_GATEWAY_SOURCE_COMMIT:-}"' in BOOTSTRAP
    assert 'ARCHIVE_REF="${SOURCE_COMMIT:-$BRANCH}"' in BOOTSTRAP
    assert 'ARCHIVE_URL="https://github.com/${REPOSITORY}/archive/${ARCHIVE_REF}.tar.gz"' in BOOTSTRAP
    assert 'SG_GATEWAY_SOURCE_COMMIT="$SOURCE_COMMIT"' in BOOTSTRAP


def test_native_installer_verifies_connections_ui_after_source_copy() -> None:
    verifier_call = 'verify_installed_connections_ui_contract "$PREFIX"'
    copy_complete = 'mv "$PREFIX.new" "$PREFIX"'
    assert verifier_call in INSTALL
    assert INSTALL.index(verifier_call) > INSTALL.index(copy_complete)


def test_current_installed_ui_satisfies_clean_install_contract(tmp_path: Path) -> None:
    prefix = _installed_tree(tmp_path)
    result = _run_ui_verifier(prefix)
    assert result.returncode == 0, result.stderr


def test_clean_install_rejects_old_hysteria2_button(tmp_path: Path) -> None:
    prefix = _installed_tree(tmp_path)
    template = prefix / "app/web/templates/connections.html"
    template.write_text(
        template.read_text(encoding="utf-8").replace(
            "data-salamander-generate>Новый пароль</button>",
            "data-salamander-generate>Сгенерировать новый</button>",
        ),
        encoding="utf-8",
    )
    result = _run_ui_verifier(prefix)
    assert result.returncode != 0
    assert "Hysteria2" in result.stderr


def test_clean_install_rejects_visible_fixed_listener_metadata(tmp_path: Path) -> None:
    prefix = _installed_tree(tmp_path)
    template = prefix / "app/web/templates/connections.html"
    template.write_text(
        template.read_text(encoding="utf-8") + "\nСистемный порт SG-Gateway\n",
        encoding="utf-8",
    )
    result = _run_ui_verifier(prefix)
    assert result.returncode != 0
    assert "fixed listener metadata" in result.stderr


def test_clean_install_rejects_old_mihomo_endpoint_block(tmp_path: Path) -> None:
    prefix = _installed_tree(tmp_path)
    template = prefix / "app/web/templates/_mihomo_panel.html"
    template.write_text(
        template.read_text(encoding="utf-8") + '\n<div class="mhv2-compact-endpoint"></div>\n',
        encoding="utf-8",
    )
    result = _run_ui_verifier(prefix)
    assert result.returncode != 0
    assert "Mihomo endpoint" in result.stderr


def test_clean_install_rejects_non_compact_hysteria2_css(tmp_path: Path) -> None:
    prefix = _installed_tree(tmp_path)
    css = prefix / "app/web/static/sg-xray-profiles-v2.css"
    css.write_text(
        css.read_text(encoding="utf-8").replace(
            "grid-template-columns: auto minmax(0, 1fr);",
            "grid-template-columns: 1fr;",
            1,
        ),
        encoding="utf-8",
    )
    result = _run_ui_verifier(prefix)
    assert result.returncode != 0
    assert "compact Hysteria2 layout" in result.stderr
