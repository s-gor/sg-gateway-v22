from pathlib import Path
import sys

root = Path(sys.argv[1])
css_path = root / "app/web/static/sg-xmux-settings-v1.css"
test_path = root / "tests/test_ui_connections_visual_v1.py"

css = css_path.read_text(encoding="utf-8")
anchor = '.xps2-salamander { grid-area: obfs; }\n'
insert = '''.xps2-salamander { grid-area: obfs; }\n\n/* Keep the three VLESS parameter strips visually identical on one-row layouts. */\n@media (min-width: 1051px) {\n  .xps2-parameter-row[data-profile-panel="reality_tcp"],\n  .xps2-parameter-row[data-profile-panel="xhttp_reality"],\n  .xps2-parameter-row[data-profile-panel="xhttp_tls"] {\n    height: 120px;\n    align-items: center;\n  }\n}\n'''
if anchor not in css:
    raise SystemExit("CSS anchor not found")
if "Keep the three VLESS parameter strips visually identical" in css:
    raise SystemExit("equal-height block already present")
css = css.replace(anchor, insert, 1)

responsive_anchor = '@media (max-width: 1050px) {\n'
responsive_insert = '''/* Compact one-row desktop keeps the same geometry without leaking into stacked layouts. */\n@media (min-width: 1051px) and (max-width: 1366px),\n       (min-width: 1051px) and (max-height: 820px) {\n  .xps2-parameter-row[data-profile-panel="reality_tcp"],\n  .xps2-parameter-row[data-profile-panel="xhttp_reality"],\n  .xps2-parameter-row[data-profile-panel="xhttp_tls"] {\n    height: 112px;\n    align-items: center;\n  }\n}\n\n@media (max-width: 1050px) {\n'''
if responsive_anchor not in css:
    raise SystemExit("responsive anchor not found")
css = css.replace(responsive_anchor, responsive_insert, 1)
css_path.write_text(css, encoding="utf-8")

test = test_path.read_text(encoding="utf-8")
append = '''\n\ndef test_first_three_xray_parameter_cards_have_equal_height_and_centered_level():\n    css = (ROOT / "app/web/static/sg-xmux-settings-v1.css").read_text(encoding="utf-8")\n    polish = css.split("SG-Gateway 022.04 · Connections controls-only polish", 1)[1]\n    selector = '.xps2-parameter-row[data-profile-panel="reality_tcp"],\\n  .xps2-parameter-row[data-profile-panel="xhttp_reality"],\\n  .xps2-parameter-row[data-profile-panel="xhttp_tls"] {'\n    assert polish.count(selector) >= 2\n    assert "@media (min-width: 1051px) {" in polish\n    assert "@media (min-width: 1051px) and (max-width: 1366px)," in polish\n    assert "(min-width: 1051px) and (max-height: 820px)" in polish\n    assert "height: 120px;" in polish\n    assert "height: 112px;" in polish\n    assert polish.count("align-items: center;") >= 2\n    assert 'data-profile-panel="hysteria2"] {\\n    height: 120px;' not in polish\n    assert 'data-profile-panel="hysteria2"] {\\n    height: 112px;' not in polish\n\n\ndef test_equal_height_rule_does_not_leak_into_stacked_981_1050_layout():\n    css = (ROOT / "app/web/static/sg-xmux-settings-v1.css").read_text(encoding="utf-8")\n    polish = css.split("SG-Gateway 022.04 · Connections controls-only polish", 1)[1]\n    stacked = polish.split("@media (max-width: 1050px)", 1)[1]\n    before_stacked = polish.split("@media (max-width: 1050px)", 1)[0]\n    assert "(min-width: 981px) and (max-width: 1366px)" in before_stacked\n    assert "(min-width: 1051px) and (max-width: 1366px)" in before_stacked\n    assert "height: 112px;" not in stacked.split("@media (max-width: 760px)", 1)[0]\n'''
if "test_first_three_xray_parameter_cards_have_equal_height_and_centered_level" in test:
    raise SystemExit("regression test already present")
test_path.write_text(test.rstrip() + append.rstrip() + "\n", encoding="utf-8")

print("Prepared equal-height VLESS parameter strips; Hysteria and stacked layouts untouched")
