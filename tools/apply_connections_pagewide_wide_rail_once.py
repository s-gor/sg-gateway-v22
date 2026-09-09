from pathlib import Path

CSS_PATH = Path('app/web/static/sg-ui-connections-v22-08.css')
XMUX_PATH = Path('app/web/templates/_xray_xmux_settings.html')
TEST_PATH = Path('tests/test_sg_gateway_v22_awg31_naiveproxy_compact_ui_02208.py')

css = CSS_PATH.read_text(encoding='utf-8')
narrow = 'calc(var(--sg-ui-card-pad, 18px) + var(--sg-ui-rail-inset, 18px))'
rail = 'var(--sg-ui-rail-inset, 18px)'

# Xray: one page-wide inner rail. xps2-panel already supplies the outer 18px boundary.
css = css.replace(
    "body.page-connections .cnv1-engine-xray .sg-ui-rail {\n  padding-inline: " + narrow + ";\n}",
    "body.page-connections .cnv1-engine-xray .sg-ui-rail {\n  padding-inline: " + rail + ";\n}",
    1,
)
css = css.replace(
    "body.page-connections .cnv1-engine-xray > .cnv1-endpoint-card {\n  margin-inline: " + narrow + ";\n}",
    "body.page-connections .cnv1-engine-xray > .cnv1-endpoint-card {\n  margin-inline: " + rail + ";\n}",
    1,
)
css = css.replace(
    "body.page-connections .cnv1-engine-xray :is(.xps2-top-actions, .xps2-actions) {\n  margin-inline: " + narrow + ";\n}",
    "body.page-connections .cnv1-engine-xray :is(.xps2-top-actions, .xps2-actions) {\n  margin-inline: 0;\n}",
    1,
)
css = css.replace(
    "body.page-connections .cnv1-engine-xray > .cnv1-advanced {\n  margin-inline: " + narrow + ";\n}",
    "body.page-connections .cnv1-engine-xray > .cnv1-advanced {\n  margin-inline: " + rail + ";\n}",
    1,
)
# AWG31 + NaiveProxy: same single 18px rail as every other section.
css = css.replace(
    "body.page-connections .cnv1-compact-protocols .sg-ui-rail {\n  padding-inline: " + narrow + ";\n}",
    "body.page-connections .cnv1-compact-protocols .sg-ui-rail {\n  padding-inline: " + rail + ";\n}",
    1,
)
CSS_PATH.write_text(css, encoding='utf-8')

# XMUX card already has its own 18px padding; remove the second rail.
xmux = XMUX_PATH.read_text(encoding='utf-8')
xmux = xmux.replace("#xray-xmux .xmux1-card > form {\n  padding-inline: var(--sg-ui-rail-inset, 18px);\n}\n\n", "", 1)
xmux = xmux.replace("  #xray-xmux .xmux1-card > form {\n    padding-inline: 0;\n  }\n", "", 1)
XMUX_PATH.write_text(xmux, encoding='utf-8')

test = TEST_PATH.read_text(encoding='utf-8')
# Remove obsolete 36px-contract tests and replace with a page-wide single-rail contract.
start = test.find('\ndef test_upper_connection_inner_rails_match_compact_protocol_inset()')
if start >= 0:
    end = test.find('\ndef ', start + 2)
    if end < 0:
        test = test[:start].rstrip() + '\n'
    else:
        test = test[:start] + test[end:]
start = test.find('\ndef test_xray_working_surfaces_follow_same_inner_rail()')
if start >= 0:
    end = test.find('\ndef ', start + 2)
    if end < 0:
        test = test[:start].rstrip() + '\n'
    else:
        test = test[:start] + test[end:]
addition = '''\n\ndef test_connections_uses_one_pagewide_inner_rail() -> None:\n    rail = 'var(--sg-ui-rail-inset, 18px)'\n    assert f'body.page-connections .cnv1-engine-xray > .cnv1-endpoint-card {{\\n  margin-inline: {rail};' in CSS\n    assert 'body.page-connections .cnv1-engine-xray :is(.xps2-top-actions, .xps2-actions) {\\n  margin-inline: 0;' in CSS\n    assert f'body.page-connections .cnv1-engine-xray > .cnv1-advanced {{\\n  margin-inline: {rail};' in CSS\n    assert f'body.page-connections .cnv1-compact-protocols .sg-ui-rail {{\\n  padding-inline: {rail};' in CSS\n    xmux = Path('app/web/templates/_xray_xmux_settings.html').read_text(encoding='utf-8')\n    assert '#xray-xmux .xmux1-card > form {' not in xmux\n'''
if 'test_connections_uses_one_pagewide_inner_rail' not in test:
    test = test.rstrip() + addition + '\n'
# Old compact test expected the former 36px composition. Update it to the single rail.
test = test.replace("assert 'padding-inline: calc(var(--sg-ui-card-pad, 18px) + var(--sg-ui-rail-inset, 18px));' in CSS", "assert 'padding-inline: var(--sg-ui-rail-inset, 18px);' in CSS")
TEST_PATH.write_text(test, encoding='utf-8')
