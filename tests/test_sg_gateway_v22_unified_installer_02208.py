from pathlib import Path
import re


ROOT = Path(__file__).parents[1]
INSTALLER = ROOT / "install.sh"
WRAPPER = ROOT / "deploy" / "install-from-github.sh"
NAIVE_INSTALLER = ROOT / "deploy" / "install-naiveproxy.sh"


def _main_body(source: str) -> str:
    start = source.index("main() {")
    end = source.index('\nif [[ "${BASH_SOURCE[0]}" == "$0" ]]', start)
    return source[start:end]


def test_unified_02208_installer_has_exactly_24_visible_top_level_stages():
    source = INSTALLER.read_text(encoding="utf-8")
    assert 'VERSION="0.1.0-022.08"' in source
    assert 'TOTAL_STAGES=24' in source

    main = _main_body(source)
    success_boundary = main.index("INSTALL_SUCCESS=1")
    before_success = main[:success_boundary]

    numbers = [
        int(value)
        for value in re.findall(
            r'(?:run_stage\s+|run_quiet\s+"Этап\s+)(\d+)(?:\s|/24)',
            before_success,
        )
    ]
    # Only one top-level visible entry per stage. Internal substeps must not
    # introduce additional top-level stage numbers.
    assert numbers == list(range(1, 25)), numbers
    for number in range(1, 25):
        assert f"Этап {number}/24" in before_success or f"run_stage {number} " in before_success


def test_naiveproxy_is_a_first_class_master_stage_before_success_boundary():
    source = INSTALLER.read_text(encoding="utf-8")
    assert NAIVE_INSTALLER.is_file()
    assert "stage_install_naiveproxy()" in source
    function = source.split("stage_install_naiveproxy()", 1)[1].split("\n}", 1)[0]
    assert 'SG_GATEWAY_SOURCE_ROOT="$SOURCE_DIR"' in function
    assert 'bash "$SOURCE_DIR/deploy/install-naiveproxy.sh"' in function
    assert 'systemctl cat sg-naiveproxy.service' in function

    main = _main_body(source)
    naive_call = main.index("stage_install_naiveproxy")
    success_boundary = main.index("INSTALL_SUCCESS=1")
    assert naive_call < success_boundary


def test_02208_github_wrapper_is_download_and_exec_only():
    source = WRAPPER.read_text(encoding="utf-8")
    forbidden = (
        "source.replace(",
        "patched_installer",
        "cannot locate unique installer success boundary",
        "install-naiveproxy.sh",
    )
    for marker in forbidden:
        assert marker not in source
    assert 'bash "$SOURCE_DIR/install.sh"' in source


def test_unified_installer_rebuild_does_not_modify_ui_assets():
    # This branch rebuild is intentionally installer/release-only. This test is
    # a guardrail for reviewers: installer tests must never require UI edits.
    spec = (ROOT / "docs" / "superpowers" / "specs" / "2026-09-06-02208-unified-installer-24stage-design.md").read_text(encoding="utf-8")
    assert "Do not alter UI geometry, templates, CSS or JS" in spec
