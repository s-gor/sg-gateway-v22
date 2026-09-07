from pathlib import Path
import re


ROOT = Path(__file__).parents[1]
INSTALL = (ROOT / "install.sh").read_text(encoding="utf-8")


def _function_body(name: str) -> str:
    match = re.search(rf"^{re.escape(name)}\(\) \{{\n(?P<body>.*?)^\}}$", INSTALL, re.M | re.S)
    assert match is not None, f"missing shell function: {name}"
    return match.group("body")


def test_stage_13_reclaims_naiveproxy_state_after_recursive_panel_chown():
    base = _function_body("stage_configuration_and_database")
    wrapper = _function_body("stage_configuration_and_database_02208")

    assert 'chown -R "$PANEL_USER":"$PANEL_GROUP" "$DATA_DIR" "$LOG_DIR"' in base
    base_call = wrapper.index("stage_configuration_and_database")
    required = (
        'install -d -o sg-naiveproxy -g sg-naiveproxy -m 0700 "$NAIVEPROXY_STATE"',
        'install -d -o sg-naiveproxy -g sg-naiveproxy -m 0750 "$NAIVEPROXY_STATE/site"',
        '"$NAIVEPROXY_STATE/xdg-data" "$NAIVEPROXY_STATE/xdg-config"',
        'chown -R sg-naiveproxy:sg-naiveproxy "$NAIVEPROXY_STATE"',
    )
    positions = []
    for line in required:
        assert line in wrapper, f"stage 13 does not reclaim NaiveProxy state: {line}"
        positions.append(wrapper.index(line))
    assert all(position > base_call for position in positions)


def test_stage_23_rejects_wrong_naiveproxy_state_ownership():
    body = _function_body("verify_naiveproxy_install_contract")
    assert "stat -c '%U:%G:%a'" in body
    assert "sg-naiveproxy:sg-naiveproxy:700" in body
    assert "sg-naiveproxy:sg-naiveproxy:750" in body
    assert '"$NAIVEPROXY_STATE/xdg-data"' in body
    assert '"$NAIVEPROXY_STATE/xdg-config"' in body
    assert 'find "$NAIVEPROXY_STATE" -xdev' in body
    assert '! -user sg-naiveproxy' in body
    assert '! -group sg-naiveproxy' in body


def test_installer_keeps_exact_24_stage_contract():
    main = _function_body("main")
    stages = [
        int(value)
        for value in re.findall(r"^  run_(?:interactive_)?stage ([0-9]+) ", main, re.M)
    ]
    assert stages == list(range(1, 25))
