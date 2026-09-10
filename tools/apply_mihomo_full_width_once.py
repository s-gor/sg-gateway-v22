from pathlib import Path

css_path = Path('app/web/static/sg-ui-connections-v22-08.css')
test_path = Path('tests/test_sg_gateway_v22_awg31_naiveproxy_compact_ui_02208.py')

css = css_path.read_text(encoding='utf-8')
old = """body.page-connections .mhv2-inner-rail {\n  padding: 0 var(--sg-ui-rail-inset, 18px) var(--sg-ui-card-pad, 18px);\n}\n"""
new = """body.page-connections .mhv2-inner-rail {\n  padding: 0 0 var(--sg-ui-card-pad, 18px);\n}\n"""
if old not in css:
    raise SystemExit('expected Mihomo inner-rail rule not found')
css = css.replace(old, new, 1)
css_path.write_text(css, encoding='utf-8')

test = test_path.read_text(encoding='utf-8')
anchor = """def test_mihomo_does_not_add_a_second_inner_rail() -> None:\n    assert 'class=\"mhv2-inner-rail\">' in MIHOMO\n    assert 'class=\"mhv2-inner-rail sg-ui-rail\">' not in MIHOMO\n"""
replacement = """def test_mihomo_does_not_add_a_second_inner_rail() -> None:\n    assert 'class=\"mhv2-inner-rail\">' in MIHOMO\n    assert 'class=\"mhv2-inner-rail sg-ui-rail\">' not in MIHOMO\n    assert 'body.page-connections .mhv2-inner-rail {\\n  padding: 0 0 var(--sg-ui-card-pad, 18px);' in CSS\n"""
if anchor not in test:
    raise SystemExit('expected Mihomo rail test not found')
test = test.replace(anchor, replacement, 1)
test_path.write_text(test, encoding='utf-8')
