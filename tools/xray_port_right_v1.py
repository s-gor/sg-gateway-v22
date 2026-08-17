import sys
from pathlib import Path

ROOT = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path(__file__).resolve().parents[1]
css_path = ROOT / "app/web/static/sg-xmux-settings-v1.css"
test_path = ROOT / "tests/test_ui_connections_visual_v1.py"

css = css_path.read_text(encoding="utf-8")
original = css

replacements = {
'''.xps2-parameter-row[data-profile-panel="xhttp_reality"] {
  grid-template-columns: minmax(300px, .9fr) minmax(150px, 210px) minmax(320px, 1.35fr);
  grid-template-areas: "title port path";
}''': '''.xps2-parameter-row[data-profile-panel="xhttp_reality"] {
  grid-template-columns: minmax(300px, .9fr) minmax(320px, 1.35fr) minmax(150px, 210px);
  grid-template-areas: "title path port";
}''',
'''.xps2-parameter-row[data-profile-panel="xhttp_tls"] {
  grid-template-columns: minmax(250px, .75fr) minmax(145px, 190px) minmax(245px, 1fr) minmax(300px, 1.2fr);
  grid-template-areas: "title port mode path";
}''': '''.xps2-parameter-row[data-profile-panel="xhttp_tls"] {
  grid-template-columns: minmax(250px, .75fr) minmax(245px, 1fr) minmax(300px, 1.2fr) minmax(145px, 190px);
  grid-template-areas: "title mode path port";
}''',
'''  .xps2-parameter-row[data-profile-panel="xhttp_reality"] {
    grid-template-columns: minmax(230px, .8fr) minmax(135px, 180px) minmax(260px, 1.25fr);
  }''': '''  .xps2-parameter-row[data-profile-panel="xhttp_reality"] {
    grid-template-columns: minmax(230px, .8fr) minmax(260px, 1.25fr) minmax(135px, 180px);
  }''',
'''  .xps2-parameter-row[data-profile-panel="xhttp_tls"] {
    grid-template-columns: minmax(220px, .75fr) minmax(130px, 175px) minmax(220px, 1fr) minmax(250px, 1.1fr);
  }''': '''  .xps2-parameter-row[data-profile-panel="xhttp_tls"] {
    grid-template-columns: minmax(220px, .75fr) minmax(220px, 1fr) minmax(250px, 1.1fr) minmax(130px, 175px);
  }''',
}
for old, new in replacements.items():
    if old not in css:
        raise SystemExit(f"expected CSS block not found:\n{old}")
    css = css.replace(old, new, 1)

# Hysteria desktop layout must remain byte-for-byte unchanged.
def block(text: str, start: str, end: str) -> str:
    a = text.index(start)
    b = text.index(end, a)
    return text[a:b]

hysteria_start = '.xps2-parameter-row[data-profile-panel="hysteria2"] {'
hysteria_end = '\n\n.xps2-salamander {'
if block(original, hysteria_start, hysteria_end) != block(css, hysteria_start, hysteria_end):
    raise SystemExit("Hysteria desktop layout changed unexpectedly")

css_path.write_text(css, encoding="utf-8")

tests = test_path.read_text(encoding="utf-8")
for old, new in (
    ('assert \'grid-template-areas: "title port path";\' in polish', 'assert \'grid-template-areas: "title path port";\' in polish'),
    ('assert \'grid-template-areas: "title port mode path";\' in polish', 'assert \'grid-template-areas: "title mode path port";\' in polish'),
):
    if old not in tests:
        raise SystemExit(f"expected test assertion not found: {old}")
    tests = tests.replace(old, new, 1)

test_path.write_text(tests, encoding="utf-8")
print("Xray port-right candidate prepared; Hysteria layout untouched")
