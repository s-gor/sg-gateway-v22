from __future__ import annotations

import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# 1) Remove the extra marketing/header layer; keep only the two protocol cards.
connections = ROOT / "app/web/templates/connections.html"
text = connections.read_text(encoding="utf-8")
old = '''  <section class="cnv1-compact-protocols cnv1-engine-card sg-ljd-card sg-ui-card sg-ui-section">
    <header class="cnv1-compact-protocols-head">
      <div>
        <div class="cnv1-card-kicker">UDP VPN + HTTPS PROXY</div>
        <h2>AmneziaWG 3.1 · NaiveProxy</h2>
        <p>Два независимых подключения в одном компактном блоке.</p>
      </div>
    </header>
    <div class="cnv1-compact-protocol-grid">
      {% include "_awg31_panel.html" %}
      {% include "_naiveproxy_panel.html" %}
    </div>
  </section>
'''
new = '''  <section class="cnv1-compact-protocols cnv1-engine-card sg-ljd-card sg-ui-card">
    <div class="cnv1-compact-protocol-grid sg-ui-rail">
      {% include "_awg31_panel.html" %}
      {% include "_naiveproxy_panel.html" %}
    </div>
  </section>
'''
assert old in text, "compact protocol wrapper drifted"
connections.write_text(text.replace(old, new, 1), encoding="utf-8")

# 2) AWG31: remove country caption that adds noise / shows "not selected".
awg = ROOT / "app/web/templates/_awg31_panel.html"
text = awg.read_text(encoding="utf-8")
text = text.replace('    <small>{{ country_name(awg31_country) }}</small>\n', '', 1)
awg.write_text(text, encoding="utf-8")

# 3) NaiveProxy: show the port in the same protocol summary line as AWG31.
naive = ROOT / "app/web/templates/_naiveproxy_panel.html"
text = naive.read_text(encoding="utf-8")
text = text.replace('<p>HTTPS proxy · TLS</p>', '<p>HTTPS proxy · TLS · порт <span data-naive-summary-port>8447</span></p>', 1)
text = text.replace("  const portChip = root.querySelector('[data-naive-port]');", "  const portChip = root.querySelector('[data-naive-port]');\n  const summaryPort = root.querySelector('[data-naive-summary-port]');", 1)
text = text.replace("    if (portChip) portChip.textContent = `${activePort}/TCP`;", "    if (portChip) portChip.textContent = `${activePort}/TCP`;\n    if (summaryPort) summaryPort.textContent = String(activePort);", 1)
naive.write_text(text, encoding="utf-8")

# 4) CSS: same horizontal rail as Mihomo; no dead header spacing.
css_path = ROOT / "app/web/static/sg-ui-connections-v22-08.css"
css = css_path.read_text(encoding="utf-8")
css = css.replace('''body.page-connections .cnv1-compact-protocols {
  padding: var(--sg-ui-card-pad, 18px);
  display: grid;
  gap: var(--sg-ui-grid-gap, 12px);
}

body.page-connections .cnv1-compact-protocols-head h2 { margin: 4px 0; }
body.page-connections .cnv1-compact-protocols-head p { margin: 0; }
''', '''body.page-connections .cnv1-compact-protocols {
  padding-block: var(--sg-ui-card-pad, 18px);
  padding-inline: 0;
  display: grid;
}

body.page-connections .cnv1-compact-protocols .sg-ui-rail {
  padding-inline: var(--sg-ui-rail-inset, 18px);
}
''', 1)
css_path.write_text(css, encoding="utf-8")

# 5) Regression contract.
test_path = ROOT / "tests/test_sg_gateway_v22_awg31_naiveproxy_compact_ui_02208.py"
test = test_path.read_text(encoding="utf-8")
extra = '''\n\ndef test_compact_protocol_polish_matches_mihomo_rail_and_removes_noise() -> None:\n    assert 'cnv1-compact-protocol-grid sg-ui-rail' in TEMPLATE\n    assert 'UDP VPN + HTTPS PROXY' not in TEMPLATE\n    assert 'AmneziaWG 3.1 · NaiveProxy' not in TEMPLATE\n    assert 'Два независимых подключения в одном компактном блоке.' not in TEMPLATE\n    assert 'country_name(awg31_country)' not in AWG31\n    assert 'HTTPS proxy · TLS · порт' in NAIVE\n    assert 'data-naive-summary-port' in NAIVE\n    assert 'padding-inline: var(--sg-ui-rail-inset, 18px);' in CSS\n'''
if 'test_compact_protocol_polish_matches_mihomo_rail_and_removes_noise' not in test:
    test += extra
test_path.write_text(test, encoding="utf-8")

# 6) Remove one-shot helpers before creating the tracked manifest.
for rel in (
    '.github/workflows/zz-compact-protocol-polish.yml',
    'tools/apply_compact_protocol_polish_once.py',
):
    p = ROOT / rel
    if p.exists():
        p.unlink()

# 7) Refresh SOURCE-SHA256SUMS from working-tree bytes.
manifest = ROOT / 'SOURCE-SHA256SUMS'
lines = []
for p in sorted(ROOT.rglob('*')):
    if not p.is_file():
        continue
    rel = p.relative_to(ROOT).as_posix()
    if rel == 'SOURCE-SHA256SUMS' or rel.startswith('.git/'):
        continue
    lines.append(f"{hashlib.sha256(p.read_bytes()).hexdigest()}  {rel}\n")
manifest.write_text(''.join(lines), encoding='utf-8')
