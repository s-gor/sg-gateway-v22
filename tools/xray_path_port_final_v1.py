import sys
from pathlib import Path

ROOT = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path(__file__).resolve().parents[1]
css_path = ROOT / "app/web/static/sg-xmux-settings-v1.css"
test_path = ROOT / "tests/test_ui_connections_visual_v1.py"

css = css_path.read_text(encoding="utf-8")
original = css

replacements = {
''' .xps2-parameter-row[data-profile-panel="xhttp_reality"] {
  grid-template-columns: minmax(250px, .75fr) minmax(245px, 1fr) minmax(300px, 1.2fr) minmax(145px, 190px);
  grid-template-areas: "title title path port";
}'''.lstrip(): '''.xps2-parameter-row[data-profile-panel="xhttp_reality"] {
  grid-template-columns: minmax(250px, .75fr) minmax(245px, 1fr) minmax(300px, 1.2fr) minmax(150px, 210px);
  grid-template-areas: "title title path port";
}''',
''' .xps2-parameter-row[data-profile-panel="xhttp_tls"] {
  grid-template-columns: minmax(250px, .75fr) minmax(245px, 1fr) minmax(300px, 1.2fr) minmax(145px, 190px);
  grid-template-areas: "title mode path port";
}'''.lstrip(): '''.xps2-parameter-row[data-profile-panel="xhttp_tls"] {
  grid-template-columns: minmax(250px, .75fr) minmax(245px, 1fr) minmax(300px, 1.2fr) minmax(150px, 210px);
  grid-template-areas: "title mode path port";
}''',
'''  .xps2-parameter-row[data-profile-panel="xhttp_reality"] {
    grid-template-columns: minmax(220px, .75fr) minmax(220px, 1fr) minmax(250px, 1.1fr) minmax(130px, 175px);
  }''': '''  .xps2-parameter-row[data-profile-panel="xhttp_reality"] {
    grid-template-columns: minmax(220px, .75fr) minmax(220px, 1fr) minmax(250px, 1.1fr) minmax(135px, 180px);
  }''',
'''  .xps2-parameter-row[data-profile-panel="xhttp_tls"] {
    grid-template-columns: minmax(220px, .75fr) minmax(220px, 1fr) minmax(250px, 1.1fr) minmax(130px, 175px);
  }''': '''  .xps2-parameter-row[data-profile-panel="xhttp_tls"] {
    grid-template-columns: minmax(220px, .75fr) minmax(220px, 1fr) minmax(250px, 1.1fr) minmax(135px, 180px);
  }''',
}

for old, new in replacements.items():
    if old not in css:
        raise SystemExit(f"expected CSS block not found:\n{old}")
    css = css.replace(old, new, 1)

path_rule = '''
@media (min-width: 1051px) {
  .xps2-parameter-row[data-profile-panel="xhttp_reality"] .xps2-field-path,
  .xps2-parameter-row[data-profile-panel="xhttp_tls"] .xps2-field-path {
    width: calc(100% - 56px);
    justify-self: center;
  }
}
'''
anchor = '\n.xps2-parameter-row[data-profile-panel="hysteria2"] {'
if path_rule.strip() not in css:
    if anchor not in css:
        raise SystemExit("Hysteria anchor not found")
    css = css.replace(anchor, path_rule + anchor, 1)

# Hysteria must remain byte-for-byte unchanged.
def block(text: str, start: str, end: str) -> str:
    a = text.index(start)
    b = text.index(end, a)
    return text[a:b]

hysteria_start = '.xps2-parameter-row[data-profile-panel="hysteria2"] {'
hysteria_end = '\n\n.xps2-salamander {'
if block(original, hysteria_start, hysteria_end) != block(css, hysteria_start, hysteria_end):
    raise SystemExit("Hysteria layout changed unexpectedly")

css_path.write_text(css, encoding="utf-8")

tests = test_path.read_text(encoding="utf-8")
anchor_test = '''def test_connections_protocol_cards_cover_low_resolution_and_mobile():\n'''
extra = '''def test_xhttp_paths_are_narrowed_symmetrically_and_ports_match_reality_tcp():\n    css = (ROOT / "app/web/static/sg-xmux-settings-v1.css").read_text(encoding="utf-8")\n    polish = css.split("SG-Gateway 022.04 · Connections controls-only polish", 1)[1]\n    assert polish.count("minmax(150px, 210px)") >= 3\n    assert polish.count("minmax(135px, 180px)") >= 3\n    assert 'width: calc(100% - 56px);' in polish\n    assert 'justify-self: center;' in polish\n    assert 'data-profile-panel="xhttp_reality"] .xps2-field-path' in polish\n    assert 'data-profile-panel="xhttp_tls"] .xps2-field-path' in polish\n\n\n'''
if extra.strip() not in tests:
    if anchor_test not in tests:
        raise SystemExit("test insertion anchor not found")
    tests = tests.replace(anchor_test, extra + anchor_test, 1)

test_path.write_text(tests, encoding="utf-8")
print("XHTTP Path narrowed symmetrically; Xray TCP ports aligned to Reality TCP; Hysteria untouched")
