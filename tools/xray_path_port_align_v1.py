import sys
from pathlib import Path

ROOT = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path(__file__).resolve().parents[1]
css_path = ROOT / "app/web/static/sg-xmux-settings-v1.css"
test_path = ROOT / "tests/test_ui_connections_visual_v1.py"

css = css_path.read_text(encoding="utf-8")
original = css

replacements = {
''' .xps2-parameter-row[data-profile-panel="xhttp_reality"] {
  grid-template-columns: minmax(300px, .9fr) minmax(320px, 1.35fr) minmax(150px, 210px);
  grid-template-areas: "title path port";
}'''.lstrip(): '''.xps2-parameter-row[data-profile-panel="xhttp_reality"] {
  grid-template-columns: minmax(250px, .75fr) minmax(245px, 1fr) minmax(300px, 1.2fr) minmax(145px, 190px);
  grid-template-areas: "title title path port";
}''',
'''  .xps2-parameter-row[data-profile-panel="xhttp_reality"] {
    grid-template-columns: minmax(230px, .8fr) minmax(260px, 1.25fr) minmax(135px, 180px);
  }''': '''  .xps2-parameter-row[data-profile-panel="xhttp_reality"] {
    grid-template-columns: minmax(220px, .75fr) minmax(220px, 1fr) minmax(250px, 1.1fr) minmax(130px, 175px);
  }''',
}

for old, new in replacements.items():
    if old not in css:
        raise SystemExit(f"expected CSS block not found:\n{old}")
    css = css.replace(old, new, 1)

# Hysteria layout must remain byte-for-byte unchanged.
def block(text: str, start: str, end: str) -> str:
    a = text.index(start)
    b = text.index(end, a)
    return text[a:b]

hysteria_start = '.xps2-parameter-row[data-profile-panel="hysteria2"] {'
hysteria_end = '\n\n.xps2-salamander {'
if block(original, hysteria_start, hysteria_end) != block(css, hysteria_start, hysteria_end):
    raise SystemExit("Hysteria layout changed unexpectedly")

# TLS layout itself remains unchanged; Reality adopts its Path/port columns.
tls_start = '.xps2-parameter-row[data-profile-panel="xhttp_tls"] {'
tls_end = '\n\n.xps2-parameter-row[data-profile-panel="hysteria2"] {'
if block(original, tls_start, tls_end) != block(css, tls_start, tls_end):
    raise SystemExit("XHTTP TLS layout changed unexpectedly")

css_path.write_text(css, encoding="utf-8")

tests = test_path.read_text(encoding="utf-8")
old_assert = '    assert \'grid-template-areas: "title path port";\' in polish\n'
new_assert = '    assert \'grid-template-areas: "title title path port";\' in polish\n'
if old_assert not in tests:
    raise SystemExit("expected Reality grid assertion not found")
tests = tests.replace(old_assert, new_assert, 1)

anchor = '''def test_connections_protocol_cards_cover_low_resolution_and_mobile():\n'''
extra = '''def test_xhttp_reality_and_tls_share_path_and_port_columns():\n    css = (ROOT / "app/web/static/sg-xmux-settings-v1.css").read_text(encoding="utf-8")\n    polish = css.split("SG-Gateway 022.04 · Connections controls-only polish", 1)[1]\n    desktop_columns = "grid-template-columns: minmax(250px, .75fr) minmax(245px, 1fr) minmax(300px, 1.2fr) minmax(145px, 190px);"\n    compact_columns = "grid-template-columns: minmax(220px, .75fr) minmax(220px, 1fr) minmax(250px, 1.1fr) minmax(130px, 175px);"\n    assert polish.count(desktop_columns) >= 2\n    assert polish.count(compact_columns) >= 2\n    assert 'grid-template-areas: "title title path port";' in polish\n    assert 'grid-template-areas: "title mode path port";' in polish\n\n\n'''
if extra.strip() not in tests:
    if anchor not in tests:
        raise SystemExit("test insertion anchor not found")
    tests = tests.replace(anchor, extra + anchor, 1)

test_path.write_text(tests, encoding="utf-8")
print("XHTTP Path/port alignment candidate prepared; Hysteria untouched")
