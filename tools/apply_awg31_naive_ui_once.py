from __future__ import annotations

import hashlib
import runpy
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

connections = ROOT / "app/web/templates/connections.html"
text = connections.read_text(encoding="utf-8")
start = text.index('  <section class="cnv1-engine-pair sg-ui-grid">')
end_marker = '  {% include "_naiveproxy_panel.html" %}\n'
end = text.index(end_marker, start) + len(end_marker)
replacement = '''  {% include "_mihomo_panel.html" %}

  <section class="cnv1-compact-protocols cnv1-engine-card sg-ljd-card sg-ui-card sg-ui-section">
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
connections.write_text(text[:start] + replacement + text[end:], encoding="utf-8")

css_path = ROOT / "app/web/static/sg-ui-connections-v22-08.css"
css = css_path.read_text(encoding="utf-8")
marker = "/* AWG31 + NaiveProxy compact protocol block */"
if marker not in css:
    css += r'''

/* AWG31 + NaiveProxy compact protocol block */
body.page-connections .cnv1-compact-protocols {
  padding: var(--sg-ui-card-pad, 18px);
  display: grid;
  gap: var(--sg-ui-grid-gap, 12px);
}

body.page-connections .cnv1-compact-protocols-head h2 { margin: 4px 0; }
body.page-connections .cnv1-compact-protocols-head p { margin: 0; }

body.page-connections .cnv1-compact-protocol-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: var(--sg-ui-grid-gap, 12px);
}

body.page-connections .cnv1-compact-protocol-card {
  position: relative;
  min-width: 0;
  padding: 14px;
  display: grid;
  align-content: start;
  gap: 12px;
}

body.page-connections .cnv1-compact-protocol-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}

body.page-connections .cnv1-compact-protocol-title {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
}

body.page-connections .cnv1-compact-protocol-title h3 { margin: 0 0 2px; }
body.page-connections .cnv1-compact-protocol-title p { margin: 0; }

body.page-connections .cnv1-compact-protocol-icon {
  width: 38px;
  height: 38px;
  flex: 0 0 38px;
  border-radius: 10px;
  display: grid;
  place-items: center;
  font-weight: 800;
  font-size: 12px;
  border: 1px solid var(--sg-ui-border, currentColor);
}

body.page-connections .cnv1-compact-protocol-endpoint {
  display: grid;
  gap: 3px;
  padding: 10px 0;
  border-top: 1px solid var(--sg-ui-border, currentColor);
  border-bottom: 1px solid var(--sg-ui-border, currentColor);
}

body.page-connections .cnv1-compact-protocol-endpoint > span,
body.page-connections .cnv1-compact-protocol-controls label > span {
  font-size: 11px;
  font-weight: 800;
  text-transform: uppercase;
  letter-spacing: .06em;
}

body.page-connections .cnv1-compact-protocol-endpoint strong { overflow-wrap: anywhere; }

body.page-connections .cnv1-compact-protocol-controls {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  align-items: end;
  gap: 10px;
}

body.page-connections .cnv1-compact-protocol-controls label {
  display: grid;
  gap: 5px;
}

body.page-connections .cnv1-compact-protocol-controls input {
  width: 100%;
  min-height: var(--sg-ui-control-height, 42px);
  border-radius: var(--sg-ui-control-radius, 9px);
}

body.page-connections .cnv1-compact-protocol-actions {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 10px;
  min-height: 42px;
}

body.page-connections .cnv1-compact-protocol-actions .xps2-naiveproxy-message { margin-right: auto; }

body.page-connections .cnv1-compact-protocol-port {
  position: absolute;
  right: 14px;
  bottom: 14px;
  font-size: 11px;
  opacity: .7;
}

body.page-connections .cnv1-compact-protocol-warning {
  margin: -4px 0 0;
  font-size: 12px;
}

@media (max-width: 900px) {
  body.page-connections .cnv1-compact-protocol-grid {
    grid-template-columns: minmax(0, 1fr);
  }
}

@media (max-width: 620px) {
  body.page-connections .cnv1-compact-protocol-head { flex-direction: column; }
  body.page-connections .cnv1-compact-protocol-controls { grid-template-columns: minmax(0, 1fr); }
  body.page-connections .cnv1-compact-protocol-actions {
    align-items: stretch;
    flex-direction: column;
  }
  body.page-connections .cnv1-compact-protocol-port { position: static; }
}
'''
css_path.write_text(css, encoding="utf-8")

# Focused GREEN check without needing pytest on the runner.
ns = runpy.run_path(str(ROOT / "tests/test_sg_gateway_v22_awg31_naiveproxy_compact_ui_02208.py"))
for name, value in ns.items():
    if name.startswith("test_") and callable(value):
        value()
print("focused compact UI contract: OK")

# Remove one-shot automation before source-integrity inventory is regenerated.
for rel in (
    ".github/workflows/zz-apply-awg31-naive-ui.yml",
    ".github/workflows/zz-awg31-naive-ui-tdd.yml",
    "tools/apply_awg31_naive_ui_once.py",
):
    path = ROOT / rel
    if path.exists():
        path.unlink()

tracked = subprocess.check_output(["git", "ls-files"], cwd=ROOT, text=True).splitlines()
rows: list[str] = []
for rel in tracked:
    if rel == "SOURCE-SHA256SUMS":
        continue
    path = ROOT / rel
    if not path.exists():
        continue
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    rows.append(f"{digest}  {rel}")
(ROOT / "SOURCE-SHA256SUMS").write_text("\n".join(sorted(rows, key=lambda row: row.split("  ", 1)[1])) + "\n", encoding="utf-8")
