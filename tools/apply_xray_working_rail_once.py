from pathlib import Path

CSS_PATH = Path('app/web/static/sg-ui-connections-v22-08.css')
TEST_PATH = Path('tests/test_sg_gateway_v22_awg31_naiveproxy_compact_ui_02208.py')

css = CSS_PATH.read_text(encoding='utf-8')
anchor = """body.page-connections .cnv1-engine-xray > .cnv1-endpoint-card {\n  margin-inline: calc(var(--sg-ui-card-pad, 18px) + var(--sg-ui-rail-inset, 18px));\n}\n"""
addition = anchor + """\nbody.page-connections .cnv1-engine-xray :is(.xps2-top-actions, .xps2-actions) {\n  margin-inline: calc(var(--sg-ui-card-pad, 18px) + var(--sg-ui-rail-inset, 18px));\n}\n\nbody.page-connections .cnv1-engine-xray > .cnv1-advanced {\n  margin-inline: calc(var(--sg-ui-card-pad, 18px) + var(--sg-ui-rail-inset, 18px));\n}\n"""
if anchor not in css:
    raise SystemExit('desktop xray endpoint rail anchor not found')
if '.cnv1-engine-xray :is(.xps2-top-actions, .xps2-actions)' not in css:
    css = css.replace(anchor, addition, 1)

mobile_anchor = """  body.page-connections .cnv1-engine-xray > .cnv1-endpoint-card {\n    margin-inline: var(--sg-ui-rail-inset, 14px);\n  }\n"""
mobile_addition = mobile_anchor + """\n\n  body.page-connections .cnv1-engine-xray :is(.xps2-top-actions, .xps2-actions),\n  body.page-connections .cnv1-engine-xray > .cnv1-advanced {\n    margin-inline: var(--sg-ui-rail-inset, 14px);\n  }\n"""
if mobile_anchor not in css:
    raise SystemExit('mobile xray endpoint rail anchor not found')
if 'body.page-connections .cnv1-engine-xray :is(.xps2-top-actions, .xps2-actions),' not in css:
    css = css.replace(mobile_anchor, mobile_addition, 1)
CSS_PATH.write_text(css, encoding='utf-8')

test = TEST_PATH.read_text(encoding='utf-8')
addition_test = """\n\ndef test_xray_action_footer_and_advanced_follow_same_working_rail() -> None:\n    desktop_inset = 'calc(var(--sg-ui-card-pad, 18px) + var(--sg-ui-rail-inset, 18px))'\n    assert f'.cnv1-engine-xray :is(.xps2-top-actions, .xps2-actions) {{\\n  margin-inline: {desktop_inset};' in CSS\n    assert f'.cnv1-engine-xray > .cnv1-advanced {{\\n  margin-inline: {desktop_inset};' in CSS\n"""
if 'test_xray_action_footer_and_advanced_follow_same_working_rail' not in test:
    TEST_PATH.write_text(test.rstrip() + addition_test + '\n', encoding='utf-8')
