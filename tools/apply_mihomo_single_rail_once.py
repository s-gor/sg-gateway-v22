from pathlib import Path

root = Path(__file__).resolve().parents[1]

tpl = root / 'app/web/templates/_mihomo_panel.html'
text = tpl.read_text(encoding='utf-8')
old = '<div class="mhv2-inner-rail sg-ui-rail">'
new = '<div class="mhv2-inner-rail">'
if old not in text:
    raise SystemExit('expected Mihomo double-rail wrapper not found')
text = text.replace(old, new, 1)
tpl.write_text(text, encoding='utf-8')

test = root / 'tests/test_sg_gateway_v22_awg31_naiveproxy_compact_ui_02208.py'
body = test.read_text(encoding='utf-8')
if 'MIHOMO = ' not in body:
    marker = 'XMUX = (ROOT / "app/web/templates/_xray_xmux_settings.html").read_text(encoding="utf-8")\n'
    body = body.replace(marker, marker + 'MIHOMO = (ROOT / "app/web/templates/_mihomo_panel.html").read_text(encoding="utf-8")\n', 1)
if 'def test_mihomo_does_not_add_a_second_inner_rail()' not in body:
    body += '\n\ndef test_mihomo_does_not_add_a_second_inner_rail() -> None:\n    assert \'class="mhv2-inner-rail">\' in MIHOMO\n    assert \'class="mhv2-inner-rail sg-ui-rail">\' not in MIHOMO\n'
test.write_text(body, encoding='utf-8')
