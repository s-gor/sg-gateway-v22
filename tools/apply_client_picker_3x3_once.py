from pathlib import Path

root = Path('.')
js_path = root / 'app/web/static/sg-device-collapse-v1.js'
css_path = root / 'app/web/static/sg-devices-v46.css'
http_path = root / 'app/naiveproxy/http.py'
test_path = root / 'tests/test_client_protocol_picker_3x3_02208.py'

js = js_path.read_text(encoding='utf-8')
# Retired AWG generations must not participate in picker ordering; NaiveProxy is the ninth current protocol.
start = js.index('  const protocolOrder = [')
end = js.index('  ];', start) + len('  ];')
js = js[:start] + '''  const protocolOrder = [
    'xray_reality_tcp',
    'xray_xhttp_reality',
    'amneziawg31',
    'mihomo',
    'xray_xhttp_tls',
    'xray_hysteria2',
    'anytls',
    'tuic',
    'naiveproxy'
  ];''' + js[end:]
# Scope unified client/device dialogs on both list and detail pages, and remove the native checkbox layout.
js = js.replace('html body.page-clients .sg-unified-dialog', 'html body .sg-unified-dialog')
js = js.replace('grid-template-columns:18px minmax(0,1fr)!important;', 'grid-template-columns:minmax(0,1fr)!important;')
old_input = 'appearance:auto!important;display:block!important;position:static!important;width:17px!important;min-width:17px!important;height:17px!important;min-height:17px!important;margin:0!important;opacity:1!important;pointer-events:auto!important;accent-color:var(--sg-blue)!important'
new_input = 'position:absolute!important;opacity:0!important;pointer-events:none!important;width:1px!important;height:1px!important;margin:0!important'
if old_input not in js:
    raise SystemExit('native checkbox rule not found')
js = js.replace(old_input, new_input)
# Recreate the compact visual checkmark inside each card, matching cv10 rather than browser-native checkbox.
needle = 'html body .sg-unified-dialog .dv16-protocol-list>.dv16-protocol>span::before,html body .sg-unified-dialog .dv16-protocol-list>.dv16-protocol>span::after{content:none!important;display:none!important}'
replacement = '''html body .sg-unified-dialog .dv16-protocol-list>.dv16-protocol>span{padding-right:34px!important;position:relative!important}
html body .sg-unified-dialog .dv16-protocol-list>.dv16-protocol>span::after{content:""!important;display:grid!important;place-items:center!important;position:absolute!important;top:50%!important;right:2px!important;width:18px!important;height:18px!important;transform:translateY(-50%)!important;border:1px solid var(--sg-line)!important;border-radius:5px!important;background:var(--sg-panel)!important;color:#fff!important;font-size:11px!important;font-weight:900!important}
html body .sg-unified-dialog .dv16-protocol-list>.dv16-protocol>input:checked+span::after{content:"✓"!important;border-color:var(--sg-blue)!important;background:var(--sg-blue)!important}'''
if needle not in js:
    raise SystemExit('pseudo-checkbox reset not found')
js = js.replace(needle, replacement)
js = js.replace('@media(min-width:981px){html body .sg-unified-dialog .dv16-protocol-list{grid-template-columns:repeat(5,minmax(0,1fr))!important}}', '@media(min-width:981px){html body .sg-unified-dialog .dv16-protocol-list{grid-template-columns:repeat(3,minmax(0,1fr))!important}}')
js_path.write_text(js, encoding='utf-8')

css = css_path.read_text(encoding='utf-8')
css = css.replace('html body.page-clients .dv16-dialog', 'html body .dv16-dialog')
css_path.write_text(css, encoding='utf-8')

http = http_path.read_text(encoding='utf-8')
old = '''        option = (
            f'<label class="cv10-protocol{locked}">'
            f'<input type="checkbox" name="protocols" value="naiveproxy"{disabled}>'
            f'<span><strong>NaiveProxy</strong><small>{note}</small></span></label>\\n      '
        )'''
new = '''        marker_at = body.index(marker)
        fieldset_at = body.rfind("<fieldset", 0, marker_at)
        fieldset_open_end = body.find(">", fieldset_at, marker_at) if fieldset_at >= 0 else -1
        fieldset_open = body[fieldset_at:fieldset_open_end + 1] if fieldset_open_end >= 0 else ""
        card_class = "dv16-protocol" if "dv16-protocol-list" in fieldset_open else "cv10-protocol"
        option = (
            f'<label class="{card_class}{locked}">'
            f'<input type="checkbox" name="protocols" value="naiveproxy"{disabled}>'
            f'<span><strong>NaiveProxy</strong><small>{note}</small></span></label>\\n      '
        )'''
if old not in http:
    raise SystemExit('NaiveProxy injector block not found')
http = http.replace(old, new)
http_path.write_text(http, encoding='utf-8')

test_path.write_text('''from pathlib import Path\n\nROOT = Path(__file__).resolve().parents[1]\nJS = (ROOT / "app/web/static/sg-device-collapse-v1.js").read_text(encoding="utf-8")\nCSS = (ROOT / "app/web/static/sg-devices-v46.css").read_text(encoding="utf-8")\nHTTP = (ROOT / "app/naiveproxy/http.py").read_text(encoding="utf-8")\nEDIT = (ROOT / "app/web/templates/_client_edit_dialogs.html").read_text(encoding="utf-8")\n\n\ndef test_current_protocol_order_is_nine_and_non_https_first():\n    start = JS.index("const protocolOrder = [")\n    end = JS.index("];", start)\n    block = JS[start:end]\n    expected = [\n        "xray_reality_tcp", "xray_xhttp_reality", "amneziawg31", "mihomo",\n        "xray_xhttp_tls", "xray_hysteria2", "anytls", "tuic", "naiveproxy",\n    ]\n    positions = [block.index(f"'{item}'") for item in expected]\n    assert positions == sorted(positions)\n    assert "'amneziawg'" not in block\n    assert "'amneziawg3'" not in block\n\n\ndef test_desktop_edit_picker_is_three_by_three_everywhere():\n    assert "repeat(3,minmax(0,1fr))!important" in JS\n    assert "repeat(5,minmax(0,1fr))!important" not in JS\n    assert "html body .dv16-dialog .dv16-protocol-list" in CSS\n\n\ndef test_edit_picker_uses_compact_visual_checks_not_native_checkbox():\n    assert "appearance:auto!important" not in JS\n    assert "input:checked+span::after" in JS\n    assert 'content:"✓"!important' in JS\n\n\ndef test_naiveproxy_injects_the_card_family_of_the_target_picker():\n    assert 'card_class = "dv16-protocol" if "dv16-protocol-list" in fieldset_open else "cv10-protocol"' in HTTP\n    assert 'f\'<label class="{card_class}{locked}">\'' in HTTP\n\n\ndef test_edit_dialogs_keep_marker_after_the_eight_static_current_cards():\n    assert EDIT.count("<!-- SG_PROTOCOL_ORDER_END -->") == 2\n    for retired in ("amneziawg\"", "amneziawg3\""):\n        assert retired not in EDIT\n''', encoding='utf-8')
