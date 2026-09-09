from pathlib import Path

CSS_PATH = Path('app/web/static/sg-ui-connections-v22-08.css')
TEST_PATH = Path('tests/test_sg_gateway_v22_awg31_naiveproxy_compact_ui_02208.py')

css = CSS_PATH.read_text(encoding='utf-8')
old = """body.page-connections .cnv1-engine-xray .sg-ui-rail {\n  padding-inline: var(--sg-ui-rail-inset, 18px);\n}\n"""
new = """body.page-connections .cnv1-engine-xray .sg-ui-rail {\n  padding-inline: calc(var(--sg-ui-card-pad, 18px) + var(--sg-ui-rail-inset, 18px));\n}\n\nbody.page-connections .cnv1-engine-xray > .cnv1-endpoint-card {\n  margin-inline: calc(var(--sg-ui-card-pad, 18px) + var(--sg-ui-rail-inset, 18px));\n}\n"""
if old not in css:
    raise SystemExit('xray desktop rail rule not found')
css = css.replace(old, new, 1)

mobile_old = """  body.page-connections .cnv1-engine-xray .sg-ui-rail {\n    padding-inline: var(--sg-ui-rail-inset, 14px);\n  }\n"""
mobile_new = """  body.page-connections .cnv1-engine-xray .sg-ui-rail {\n    padding-inline: var(--sg-ui-rail-inset, 14px);\n  }\n\n  body.page-connections .cnv1-engine-xray > .cnv1-endpoint-card {\n    margin-inline: var(--sg-ui-rail-inset, 14px);\n  }\n"""
if mobile_old not in css:
    raise SystemExit('xray mobile rail rule not found')
css = css.replace(mobile_old, mobile_new, 1)
CSS_PATH.write_text(css, encoding='utf-8')

test = TEST_PATH.read_text(encoding='utf-8')
addition = """\n\ndef test_upper_connection_inner_rails_match_compact_protocol_inset() -> None:\n    desktop_inset = 'calc(var(--sg-ui-card-pad, 18px) + var(--sg-ui-rail-inset, 18px))'\n    assert f'body.page-connections .cnv1-engine-xray .sg-ui-rail {{\\n  padding-inline: {desktop_inset};' in CSS\n    assert f'body.page-connections .cnv1-engine-xray > .cnv1-endpoint-card {{\\n  margin-inline: {desktop_inset};' in CSS\n    assert f'body.page-connections .cnv1-compact-protocols .sg-ui-rail {{\\n  padding-inline: {desktop_inset};' in CSS\n"""
if 'test_upper_connection_inner_rails_match_compact_protocol_inset' not in test:
    TEST_PATH.write_text(test.rstrip() + addition + '\n', encoding='utf-8')
