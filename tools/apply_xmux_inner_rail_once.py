from pathlib import Path

XMUX_PATH = Path('app/web/templates/_xray_xmux_settings.html')
TEST_PATH = Path('tests/test_sg_gateway_v22_awg31_naiveproxy_compact_ui_02208.py')

xmux = XMUX_PATH.read_text(encoding='utf-8')
needle = """#xray-xmux .xmux1-card {\n  padding: 16px 18px 14px;\n}\n"""
replacement = """#xray-xmux .xmux1-card {\n  padding: 16px 18px 14px;\n}\n\n#xray-xmux .xmux1-card > form {\n  padding-inline: var(--sg-ui-rail-inset, 18px);\n}\n"""
if needle not in xmux:
    raise SystemExit('XMUX card rule not found')
xmux = xmux.replace(needle, replacement, 1)

mobile_needle = """@media (max-width: 760px) {\n  #xray-xmux .xmux1-head {\n"""
mobile_replacement = """@media (max-width: 760px) {\n  #xray-xmux .xmux1-card > form {\n    padding-inline: 0;\n  }\n\n  #xray-xmux .xmux1-head {\n"""
if mobile_needle not in xmux:
    raise SystemExit('XMUX mobile media rule not found')
xmux = xmux.replace(mobile_needle, mobile_replacement, 1)
XMUX_PATH.write_text(xmux, encoding='utf-8')

test = TEST_PATH.read_text(encoding='utf-8')
if 'XMUX =' not in test:
    test = test.replace(
        "CSS = (ROOT / \"app/web/static/sg-ui-connections-v22-08.css\").read_text(encoding=\"utf-8\")\n",
        "CSS = (ROOT / \"app/web/static/sg-ui-connections-v22-08.css\").read_text(encoding=\"utf-8\")\nXMUX = (ROOT / \"app/web/templates/_xray_xmux_settings.html\").read_text(encoding=\"utf-8\")\n",
        1,
    )
addition = """\n\ndef test_xmux_inner_controls_follow_the_same_desktop_rail() -> None:\n    assert '#xray-xmux .xmux1-card > form {' in XMUX\n    assert 'padding-inline: var(--sg-ui-rail-inset, 18px);' in XMUX\n    assert '@media (max-width: 760px)' in XMUX\n    assert 'padding-inline: 0;' in XMUX\n"""
if 'test_xmux_inner_controls_follow_the_same_desktop_rail' not in test:
    test = test.rstrip() + addition + '\n'
TEST_PATH.write_text(test, encoding='utf-8')
