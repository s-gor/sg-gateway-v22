import sys
from pathlib import Path

ROOT = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path(__file__).resolve().parents[1]
template_path = ROOT / "app/web/templates/connections.html"
css_path = ROOT / "app/web/static/sg-xmux-settings-v1.css"
test_path = ROOT / "tests/test_ui_connections_visual_v1.py"

template = template_path.read_text(encoding="utf-8")
css = css_path.read_text(encoding="utf-8")
tests = test_path.read_text(encoding="utf-8")

template = template.replace(
    "<p>Здесь только то, что можно изменить. Фиксированные параметры показаны компактно рядом с названием профиля.</p>",
    "<p>Здесь только то, что можно изменить.</p>",
    1,
)

old_meta = '''                  <div class="xps2-profile-meta">\n                    {% if profile.flow %}<span>Vision · {{ profile.flow }}</span>{% endif %}\n                    {% if profile.id == 'xhttp_reality' %}<span>XHTTP client · stream-one</span>{% endif %}\n                    {% if profile.encryption_required %}<span class="{{ 'is-ready' if profile.encryption_ready else 'is-warning' }}">VLESS Encryption · {{ 'готово' if profile.encryption_ready else 'не создано' }}</span>{% endif %}\n                    {% if not profile.path %}<span>Path · —</span>{% endif %}\n                  </div>'''
new_meta = '''                  {% if profile.id == 'hysteria2' %}\n                  <div class="xps2-profile-meta">\n                    {% if not profile.path %}<span>Path · —</span>{% endif %}\n                  </div>\n                  {% endif %}'''
if old_meta not in template:
    raise SystemExit("profile metadata block not found")
template = template.replace(old_meta, new_meta, 1)

old_path = '''                {% if profile.path %}\n                <label class="xps2-field-path">\n                  <span>Public Path</span>\n                  <input type="text" name="{{ profile.id }}_path" value="{{ profile.path }}"\n                         {% if locked %}disabled{% endif %}>\n                </label>\n                {% endif %}'''
new_path = '''                {% if profile.path %}\n                <input type="hidden" name="{{ profile.id }}_path" value="{{ profile.path }}">\n                {% endif %}'''
if old_path not in template:
    raise SystemExit("visible Public Path block not found")
template = template.replace(old_path, new_path, 1)
template_path.write_text(template, encoding="utf-8")

replacements = {
'''.xps2-field-port { grid-area: port; }\n.xps2-field-mode { grid-area: mode; }\n.xps2-field-path { grid-area: path; }\n.xps2-parameter-title { grid-area: title; }''': '''.xps2-field-port { grid-area: port; }\n.xps2-field-mode { grid-area: mode; }\n.xps2-parameter-title { grid-area: title; }''',
'''.xps2-parameter-row[data-profile-panel="xhttp_reality"] {\n  grid-template-columns: minmax(250px, .75fr) minmax(245px, 1fr) minmax(300px, 1.2fr) minmax(150px, 210px);\n  grid-template-areas: "title title path port";\n}\n\n.xps2-parameter-row[data-profile-panel="xhttp_tls"] {\n  grid-template-columns: minmax(250px, .75fr) minmax(245px, 1fr) minmax(300px, 1.2fr) minmax(150px, 210px);\n  grid-template-areas: "title mode path port";\n}\n\n@media (min-width: 1051px) {\n  .xps2-parameter-row[data-profile-panel="xhttp_reality"] .xps2-field-path,\n  .xps2-parameter-row[data-profile-panel="xhttp_tls"] .xps2-field-path {\n    width: calc(100% - 56px);\n    justify-self: center;\n  }\n}\n''': '''.xps2-parameter-row[data-profile-panel="xhttp_reality"] {\n  grid-template-columns: minmax(300px, 1fr) minmax(150px, 210px);\n  grid-template-areas: "title port";\n}\n\n.xps2-parameter-row[data-profile-panel="xhttp_tls"] {\n  grid-template-columns: minmax(250px, .8fr) minmax(320px, 1.2fr) minmax(150px, 210px);\n  grid-template-areas: "title mode port";\n}\n''',
'''  .xps2-parameter-row[data-profile-panel="xhttp_reality"] {\n    grid-template-columns: minmax(220px, .75fr) minmax(220px, 1fr) minmax(250px, 1.1fr) minmax(135px, 180px);\n  }\n\n  .xps2-parameter-row[data-profile-panel="xhttp_tls"] {\n    grid-template-columns: minmax(220px, .75fr) minmax(220px, 1fr) minmax(250px, 1.1fr) minmax(135px, 180px);\n  }''': '''  .xps2-parameter-row[data-profile-panel="xhttp_reality"] {\n    grid-template-columns: minmax(230px, 1fr) minmax(135px, 180px);\n  }\n\n  .xps2-parameter-row[data-profile-panel="xhttp_tls"] {\n    grid-template-columns: minmax(210px, .8fr) minmax(260px, 1.2fr) minmax(135px, 180px);\n  }''',
'''  .xps2-parameter-row[data-profile-panel="xhttp_reality"] {\n    grid-template-areas:\n      "title port"\n      "path path";\n  }\n\n  .xps2-parameter-row[data-profile-panel="xhttp_tls"] {\n    grid-template-areas:\n      "title port"\n      "mode path";\n  }''': '''  .xps2-parameter-row[data-profile-panel="xhttp_reality"] {\n    grid-template-areas:\n      "title port";\n  }\n\n  .xps2-parameter-row[data-profile-panel="xhttp_tls"] {\n    grid-template-areas:\n      "title port"\n      "mode mode";\n  }''',
'''  .xps2-parameter-row[data-profile-panel="xhttp_reality"] {\n    grid-template-areas: "title" "port" "path";\n  }\n\n  .xps2-parameter-row[data-profile-panel="xhttp_tls"] {\n    grid-template-areas: "title" "port" "mode" "path";\n  }''': '''  .xps2-parameter-row[data-profile-panel="xhttp_reality"] {\n    grid-template-areas: "title" "port";\n  }\n\n  .xps2-parameter-row[data-profile-panel="xhttp_tls"] {\n    grid-template-areas: "title" "port" "mode";\n  }''',
}
for old, new in replacements.items():
    if old not in css:
        raise SystemExit(f"expected CSS block not found:\n{old}")
    css = css.replace(old, new, 1)
css_path.write_text(css, encoding="utf-8")

start = tests.index("def test_connections_protocol_cards_show_only_real_controls_as_fields():")
end = tests.index("def test_connections_protocol_cards_cover_low_resolution_and_mobile():")
new_tests = '''def test_connections_protocol_cards_show_only_real_controls_as_fields():\n    template = (ROOT / "app/web/templates/connections.html").read_text(encoding="utf-8")\n    css = (ROOT / "app/web/static/sg-xmux-settings-v1.css").read_text(encoding="utf-8")\n    polish = css.split("SG-Gateway 022.04 · Connections controls-only polish", 1)[1]\n    assert "Здесь только то, что можно изменить" in template\n    assert "Public Path" not in template\n    assert "Vision · {{ profile.flow }}" not in template\n    assert "XHTTP client · stream-one" not in template\n    assert "VLESS Encryption ·" not in template\n    assert "xps2-field-path" not in template\n    assert '<input type="hidden" name="{{ profile.id }}_path" value="{{ profile.path }}">' in template\n    assert "xps2-field-port" in template\n    assert "xps2-field-mode" in template\n    assert ".xps2-field-port" in polish\n    assert ".xps2-field-mode" in polish\n\n\ndef test_reality_xhttp_fixed_mode_is_native_hidden_form_value_not_fake_control():\n    template = (ROOT / "app/web/templates/connections.html").read_text(encoding="utf-8")\n    js = (ROOT / "app/web/static/sg-xmux-settings-v1.js").read_text(encoding="utf-8")\n    assert "{% if profile.id == 'xhttp_reality' %}" in template\n    assert '<input type="hidden" name="{{ profile.id }}_mode" value="stream-one">' in template\n    assert "data-xmux-reality-fixed" not in js\n    assert "label.replaceWith" not in js\n    assert "Reality XHTTP mode is rendered by the main form as a hidden stream-one" in js\n\n\ndef test_connections_protocol_cards_keep_all_mutable_form_contracts():\n    template = (ROOT / "app/web/templates/connections.html").read_text(encoding="utf-8")\n    for field in (\n        'name="{{ profile.id }}_port"',\n        'name="{{ profile.id }}_mode"',\n        'name="{{ profile.id }}_path"',\n        'name="hysteria2_obfs_mode"',\n        'name="hysteria2_obfs_password"',\n        'name="hysteria2_obfs_rotate"',\n    ):\n        assert field in template\n    for value in ('value="none"', 'value="salamander"', 'value="gecko"'):\n        assert value in template\n    assert "Проверить конфигурацию" in template\n    assert "Сохранить и применить" in template\n\n\ndef test_connections_protocol_cards_have_minimal_profile_specific_grids():\n    css = (ROOT / "app/web/static/sg-xmux-settings-v1.css").read_text(encoding="utf-8")\n    polish = css.split("SG-Gateway 022.04 · Connections controls-only polish", 1)[1]\n    for profile_id in ("reality_tcp", "xhttp_reality", "xhttp_tls", "hysteria2"):\n        assert f'data-profile-panel="{profile_id}"' in polish\n    assert polish.count('grid-template-areas: "title port";') >= 2\n    assert 'grid-template-areas: "title mode port";' in polish\n    assert '"obfs obfs"' in polish\n    assert "path port" not in polish\n    assert ".xps2-field-path" not in polish\n    assert "box-shadow: none" in polish\n\n\ndef test_first_three_xray_cards_keep_ports_aligned_and_tls_mode_only():\n    css = (ROOT / "app/web/static/sg-xmux-settings-v1.css").read_text(encoding="utf-8")\n    polish = css.split("SG-Gateway 022.04 · Connections controls-only polish", 1)[1]\n    assert polish.count("minmax(150px, 210px)") >= 3\n    assert polish.count("minmax(135px, 180px)") >= 3\n    assert 'grid-template-areas: "title mode port";' in polish\n\n\n'''
tests = tests[:start] + new_tests + tests[end:]
tests = tests.replace(
    '    assert \'grid-template-areas: "title" "port" "mode" "path";\' in polish\n',
    '    assert \'grid-template-areas: "title" "port" "mode";\' in polish\n',
    1,
)
test_path.write_text(tests, encoding="utf-8")

print("Minimal Xray controls prepared; Hysteria markup and layout left unchanged")
