from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
WRAPPER = (ROOT / "deploy" / "update-from-github-02207.sh").read_text(
    encoding="utf-8"
)


def _shell_function(name: str) -> str:
    match = re.search(
        rf"(?ms)^{re.escape(name)}\(\) \{{\n.*?^\}}$",
        WRAPPER,
    )
    assert match is not None, f"shell function is missing: {name}"
    return match.group(0)


def test_wrapper_stages_exact_naiveproxy_hostd_unit() -> None:
    function = _shell_function("stage_naive_hostd_unit")
    assert "${SOURCE_COMMIT}/hostd/systemd/sg-hostd.service" in function
    assert '"$PREFIX/hostd/systemd/sg-hostd.service"' in function
    assert "ReadWritePaths=-/run/sg-gateway" in function
    assert "Environment=PYTHONPATH=/opt/sg-gateway:/opt/sg-gateway/hostd" in function


def test_hostd_unit_staging_is_inside_rollback_protected_stage() -> None:
    function = _shell_function("run_naive_stage")
    assert function.index("stage_naive_hostd_unit") < function.index(
        "install-naiveproxy.sh"
    )


def test_safety_backup_resolution_binds_exact_source_commit() -> None:
    function = _shell_function("resolve_safety_backup")
    assert 'payload.get("commit")' in function
    assert "SOURCE_COMMIT" in function
