from pathlib import Path
import sys

root = Path(sys.argv[1])
template_path = root / "app/web/templates/connections.html"
css_path = root / "app/web/static/sg-awg-dual-v1.css"
test_path = root / "tests/test_awg_style_ui.py"

template = template_path.read_text(encoding="utf-8")
runtime_note = '          <p class="awgd-runtime-note"><strong>Отдельный runtime.</strong> Интерфейс <code>awg3</code>, собственные ключи и сеть 10.67.0.0/16. Глобальный AWG2 runtime не изменяется.</p>\n'
if template.count(runtime_note) != 1:
    raise SystemExit("expected exactly one AWG3 runtime note")
template = template.replace(runtime_note, "")
template_path.write_text(template, encoding="utf-8")

css = css_path.read_text(encoding="utf-8")
blocks = [
    '.page-connections .awgd-card-v3::before { background: linear-gradient(90deg, var(--sg-blue), var(--sg-green), transparent 82%); }\n',
    '.page-connections .awgd-card-v3 .awgd-generation { border-color: color-mix(in srgb, var(--sg-blue) 40%, var(--sg-line)); background: color-mix(in srgb, var(--sg-blue) 9%, var(--sg-panel-soft)); color: var(--sg-blue); }\n',
    '.page-connections .awgd-runtime-note { margin: 0 16px 2px; border: 1px solid var(--sg-line-soft); border-radius: 10px; background: var(--sg-panel-soft); padding: 10px 12px; color: var(--sg-muted); font-size: 9px; line-height: 1.45; }\n',
    '.page-connections .awgd-runtime-note strong { color: var(--sg-text); }\n',
]
for block in blocks:
    if css.count(block) != 1:
        raise SystemExit(f"expected exactly one CSS block: {block[:80]!r}")
    css = css.replace(block, "")
marker = '/* SG-Gateway 022.04 · AWG2/AWG3 symmetric cards: one visual contract. */\n'
anchor = '/* SG-Gateway Fix29 — dual AWG presentation. Scoped to Connections. */\n'
if marker not in css:
    if anchor not in css:
        raise SystemExit("AWG CSS anchor not found")
    css = css.replace(anchor, anchor + marker, 1)
css_path.write_text(css, encoding="utf-8")

tests = test_path.read_text(encoding="utf-8")
if not tests.startswith("from pathlib import Path\n"):
    tests = "from pathlib import Path\n\n" + tests
addition = '''\n\ndef test_awg3_uses_the_same_visual_card_contract_as_awg2():\n    root = Path(__file__).resolve().parents[1]\n    template = (root / "app/web/templates/connections.html").read_text(encoding="utf-8")\n    css = (root / "app/web/static/sg-awg-dual-v1.css").read_text(encoding="utf-8")\n\n    assert 'class="awgd-card awgd-card-v2"' in template\n    assert 'class="awgd-card awgd-card-v3"' in template\n    assert "awgd-runtime-note" not in template\n    assert "Отдельный runtime." not in template\n    assert ".awgd-card-v3::before" not in css\n    assert ".awgd-card-v3 .awgd-generation" not in css\n    assert "AWG2/AWG3 symmetric cards: one visual contract" in css\n'''
if "def test_awg3_uses_the_same_visual_card_contract_as_awg2():" in tests:
    raise SystemExit("symmetry test already exists")
tests += addition
test_path.write_text(tests, encoding="utf-8")

print("AWG3 symmetry candidate prepared")
