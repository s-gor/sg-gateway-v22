from pathlib import Path
import sys

root = Path(sys.argv[1])
css_path = root / "app/web/static/sg-xmux-settings-v1.css"
test_path = root / "tests/test_ui_connections_visual_v1.py"

css = css_path.read_text(encoding="utf-8")
anchor = '.xps2-salamander { grid-area: obfs; }\n'
insert = '''.xps2-salamander { grid-area: obfs; }\n\n/* Keep the three VLESS parameter strips visually identical on desktop. */\n@media (min-width: 1051px) {\n  .xps2-parameter-row[data-profile-panel="reality_tcp"],\n  .xps2-parameter-row[data-profile-panel="xhttp_reality"],\n  .xps2-parameter-row[data-profile-panel="xhttp_tls"] {\n    height: 120px;\n    align-items: center;\n  }\n}\n'''
if anchor not in css:
    raise SystemExit("CSS anchor not found")
if "Keep the three VLESS parameter strips visually identical" in css:
    raise SystemExit("equal-height block already present")
css = css.replace(anchor, insert, 1)

low_anchor = '''  .xps2-parameter-row {\n    gap: 9px 11px;\n    padding: 11px 12px;\n  }\n'''
low_insert = '''  .xps2-parameter-row {\n    gap: 9px 11px;\n    padding: 11px 12px;\n  }\n\n  .xps2-parameter-row[data-profile-panel="reality_tcp"],\n  .xps2-parameter-row[data-profile-panel="xhttp_reality"],\n  .xps2-parameter-row[data-profile-panel="xhttp_tls"] {\n    height: 112px;\n    align-items: center;\n  }\n'''
if low_anchor not in css:
    raise SystemExit("low-resolution anchor not found")
css = css.replace(low_anchor, low_insert, 1)
css_path.write_text(css, encoding="utf-8")

test = test_path.read_text(encoding="utf-8")
append = '''\n\ndef test_first_three_xray_parameter_cards_have_equal_height_and_centered_level():\n    css = (ROOT / "app/web/static/sg-xmux-settings-v1.css").read_text(encoding="utf-8")\n    polish = css.split("SG-Gateway 022.04 · Connections controls-only polish", 1)[1]\n    desktop = polish.split("@media (min-width: 1051px)", 1)[1].split("@media", 1)[0]\n    for profile_id in ("reality_tcp", "xhttp_reality", "xhttp_tls"):\n        assert f'data-profile-panel="{profile_id}"' in desktop\n    assert 'data-profile-panel="hysteria2"' not in desktop\n    assert "height: 120px;" in desktop\n    assert "align-items: center;" in desktop\n    low = polish.split("@media (min-width: 981px) and (max-width: 1366px)", 1)[1].split("@media (max-width: 1050px)", 1)[0]\n    assert "height: 112px;" in low\n    assert "align-items: center;" in low\n'''
if "test_first_three_xray_parameter_cards_have_equal_height_and_centered_level" in test:
    raise SystemExit("regression test already present")
test_path.write_text(test.rstrip() + append + "\n", encoding="utf-8")

print("Prepared equal-height VLESS parameter strips; Hysteria untouched")
