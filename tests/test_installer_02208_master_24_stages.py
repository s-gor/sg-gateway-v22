from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]


def _master() -> str:
    return (ROOT / "install.sh").read_text(encoding="utf-8")


def test_master_exposes_exactly_24_numbered_stages():
    source = _master()
    assert "TOTAL_STAGES=24" in source
    main = source[source.index("main() {") :]
    numbers = [
        int(value)
        for value in re.findall(r"\b(?:run_stage|run_interactive_stage)\s+(\d+)\s+", main)
    ]
    assert numbers == list(range(1, 25)), numbers


def test_interactive_parameter_stage_runs_in_foreground():
    source = _master()
    assert "run_interactive_stage()" in source
    assert (
        'run_interactive_stage 2 "Определение режима и параметров" '
        "stage_prepare_install_context"
    ) in source
    assert (
        'run_stage 2 "Определение режима и параметров" stage_prepare_install_context'
        not in source
    )


def test_naiveproxy_is_a_native_master_stage_not_a_wrapper_injection():
    source = _master()
    assert 'NAIVEPROXY_VERSION="v2.11.2-naive"' in source
    assert 'NAIVEPROXY_PORT="8447"' in source
    assert "stage_naiveproxy_runtime()" in source
    assert 'run_stage 11 "NaiveProxy runtime" stage_naiveproxy_runtime' in source
    assert 'deploy/install-naiveproxy.sh' not in source
    assert 'sg-gateway-naiveproxy.service' in source
    assert '"${NAIVEPROXY_PORT}/tcp"' in source


def test_naiveproxy_is_part_of_backup_rollback_and_final_contract():
    source = _master()
    assert "etc/systemd/system/sg-gateway-naiveproxy.service" in source
    assert "etc/sg-gateway/naiveproxy" in source
    assert "sg-gateway-naiveproxy.service" in source[source.index("create_backup()") :]
    assert "verify_naiveproxy_install_contract()" in source
    assert 'run_stage 23 "Проверка NaiveProxy" verify_naiveproxy_install_contract' in source
