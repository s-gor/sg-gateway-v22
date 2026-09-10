from pathlib import Path

panel = Path('app/web/templates/_mihomo_panel.html')
text = panel.read_text(encoding='utf-8')
old = '''            <label class="mhv2-check">\n              <input type="checkbox" name="mieru_user_hint_mandatory"\n                     {% if mihomo.settings.mieru_user_hint_mandatory %}checked{% endif %}>\n              <span>Требовать user hint</span>\n            </label>'''
new = '''            <label class="mhv2-user-hint-switch">\n              <span>Требовать user hint</span>\n              <span class="sg-runtime-switch mhv2-user-hint-control">\n                <input type="checkbox" name="mieru_user_hint_mandatory"\n                       {% if mihomo.settings.mieru_user_hint_mandatory %}checked{% endif %}>\n                <span class="sg-runtime-track" aria-hidden="true"><i></i></span>\n              </span>\n            </label>'''
if old not in text:
    raise SystemExit('Mieru user hint checkbox block not found')
panel.write_text(text.replace(old, new, 1), encoding='utf-8')

css = Path('app/web/static/sg-ui-connections-v22-08.css')
ct = css.read_text(encoding='utf-8')
append = '''\n/* Mieru user-hint toggle: use the same compact switch language as protocol controls. */\nbody.page-connections .mhv2-user-hint-switch {\n  display: flex;\n  align-items: center;\n  justify-content: space-between;\n  gap: 12px;\n  min-height: 34px;\n  margin-top: 2px;\n  font-weight: 700;\n}\n\nbody.page-connections .mhv2-user-hint-control {\n  flex: 0 0 auto;\n}\n\nbody.page-connections .mhv2-user-hint-control .sg-runtime-copy {\n  display: none;\n}\n'''
if '/* Mieru user-hint toggle:' not in ct:
    css.write_text(ct.rstrip() + '\n' + append, encoding='utf-8')

# Keep the focused UI contract from regressing to a native checkbox presentation.
test = Path('tests/test_sg_gateway_v22_awg31_naiveproxy_compact_ui_02208.py')
tt = test.read_text(encoding='utf-8')
addition = '''\n\ndef test_mieru_user_hint_uses_compact_switch_not_native_checkbox_row() -> None:\n    assert 'class="mhv2-user-hint-switch"' in MIHOMO\n    assert 'class="sg-runtime-switch mhv2-user-hint-control"' in MIHOMO\n    assert 'name="mieru_user_hint_mandatory"' in MIHOMO\n    assert 'class="mhv2-check"' not in MIHOMO\n    assert '.mhv2-user-hint-switch {' in CSS\n'''
if 'test_mieru_user_hint_uses_compact_switch_not_native_checkbox_row' not in tt:
    test.write_text(tt.rstrip() + addition + '\n', encoding='utf-8')
