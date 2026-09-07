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
        'install -d -o "$NAIVEPROXY_USER" -g "$NAIVEPROXY_GROUP" -m 0700 "$NAIVEPROXY_STATE"',
        'install -d -o "$NAIVEPROXY_USER" -g "$NAIVEPROXY_GROUP" -m 0700 "$NAIVEPROXY_STATE/xdg-data"',
        'install -d -o "$NAIVEPROXY_USER" -g "$NAIVEPROXY_GROUP" -m 0700 "$NAIVEPROXY_STATE/xdg-config"',
    )

    positions = []
    for line in required:
        assert line in wrapper, f"stage 13 does not restore NaiveProxy ownership: {line}"
        positions.append(wrapper.index(line))

    assert all(position > base_call for position in positions)


def test_runtime_verification_checks_naiveproxy_state_ownership():
    body = _function_body("verify_naiveproxy_runtime")
    assert 'sg-naiveproxy:sg-naiveproxy:700' in body
    assert 'stat -c' in body
    assert '"$NAIVEPROXY_STATE/xdg-data"' in body
    assert '"$NAIVEPROXY_STATE/xdg-config"' in body
