from pathlib import Path

root = Path(__file__).resolve().parents[1]
connections = root / "app/web/templates/connections.html"
mihomo = root / "app/web/templates/_mihomo_panel.html"
css = root / "app/web/static/sg-ui-connections-v22-08.css"
test = root / "tests/test_sg_gateway_v22_awg31_naiveproxy_compact_ui_02208.py"

text = connections.read_text(encoding="utf-8")
old = '''  <section class="cnv1-compact-protocols cnv1-engine-card sg-ljd-card sg-ui-card">\n    <div class="cnv1-compact-protocol-grid sg-ui-rail">\n      {% include "_awg31_panel.html" %}\n      {% include "_naiveproxy_panel.html" %}\n    </div>\n  </section>'''
new = '''  <section class="cnv1-compact-protocols cnv1-engine-card sg-ljd-card sg-ui-card sg-ui-section">\n    <header class="cnv1-engine-head cnv1-peer-engine-head">\n      <div class="cnv1-engine-title">\n        <div class="cnv1-engine-logo awg">\n          <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 12h4l2-5 4 10 2-5h4"/></svg>\n        </div>\n        <div>\n          <div class="cnv1-card-kicker">UDP VPN · HTTPS PROXY</div>\n          <h2>AmneziaWG 3.1 · NaiveProxy</h2>\n          <p>Два независимых подключения SG-Gateway.</p>\n        </div>\n      </div>\n      <span class="cnv1-port-chip">2 протокола</span>\n    </header>\n    <div class="cnv1-compact-protocol-grid sg-ui-rail">\n      {% include "_awg31_panel.html" %}\n      {% include "_naiveproxy_panel.html" %}\n    </div>\n  </section>'''
if old not in text:
    raise SystemExit("compact protocol block anchor not found")
connections.write_text(text.replace(old, new, 1), encoding="utf-8")

text = mihomo.read_text(encoding="utf-8")
text = text.replace(
    '<section class="mhv2-panel cnv1-engine-card cnv1-engine-mihomo sg-ljd-card" id="mihomo">',
    '<section class="mhv2-panel cnv1-engine-card cnv1-engine-mihomo sg-ljd-card sg-ui-card sg-ui-section" id="mihomo">',
    1,
)
text = text.replace(
    '  <header class="mhv2-head">\n    <div>\n      <div class="mhv2-kicker">MIHOMO + SING-BOX</div>',
    '  <header class="mhv2-head cnv1-engine-head cnv1-peer-engine-head">\n    <div class="cnv1-engine-title">\n      <div class="cnv1-engine-logo mihomo">\n        <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 7h14M5 12h14M5 17h14"/></svg>\n      </div>\n      <div>\n        <div class="mhv2-kicker cnv1-card-kicker">MIHOMO + SING-BOX</div>',
    1,
)
text = text.replace(
    '      <p>Три независимых listener двух движков.</p>\n    </div>\n    <span class="mhv2-state',
    '        <p>Три независимых listener двух движков.</p>\n      </div>\n    </div>\n    <span class="mhv2-state',
    1,
)
mihomo.write_text(text, encoding="utf-8")

styles = css.read_text(encoding="utf-8")
marker = '/* Unified engine shells: Xray, Mihomo and AWG31/NaiveProxy share one outer-card language. */'
if marker not in styles:
    styles += '''\n\n/* Unified engine shells: Xray, Mihomo and AWG31/NaiveProxy share one outer-card language. */\nbody.page-connections :is(\n  .mhv2-panel.cnv1-engine-card,\n  .cnv1-compact-protocols.cnv1-engine-card\n) {\n  padding: 0;\n  overflow: hidden;\n  border: 1px solid var(--sg-line);\n  border-radius: var(--sg-ui-card-radius, 15px);\n  background: var(--sg-panel);\n  box-shadow: inset 0 1px rgba(255,255,255,.018);\n}\n\nbody.page-connections .mhv2-head.cnv1-engine-head,\nbody.page-connections .cnv1-compact-protocols > .cnv1-engine-head {\n  margin: 0;\n  padding: var(--sg-ui-card-pad, 18px);\n}\n\nbody.page-connections .cnv1-engine-logo.mihomo {\n  border: 1px solid color-mix(in srgb, var(--sg-blue) 28%, transparent);\n  background: color-mix(in srgb, var(--sg-blue) 12%, transparent);\n  color: var(--sg-blue);\n}\n\nbody.page-connections .cnv1-compact-protocols {\n  padding-block: 0;\n}\n\nbody.page-connections .cnv1-compact-protocols .sg-ui-rail {\n  padding: 0 var(--sg-ui-rail-inset, 18px) var(--sg-ui-card-pad, 18px);\n}\n\nbody.page-connections .mhv2-inner-rail {\n  padding: 0 var(--sg-ui-rail-inset, 18px) var(--sg-ui-card-pad, 18px);\n}\n\n@media (max-width: 620px) {\n  body.page-connections .cnv1-compact-protocols .sg-ui-rail,\n  body.page-connections .mhv2-inner-rail {\n    padding-inline: var(--sg-ui-rail-inset, 14px);\n  }\n}\n'''
css.write_text(styles, encoding="utf-8")

checks = test.read_text(encoding="utf-8")
if 'def test_lower_engine_shells_match_xray_outer_card_language()' not in checks:
    checks += '''\n\ndef test_lower_engine_shells_match_xray_outer_card_language() -> None:\n    assert 'mhv2-head cnv1-engine-head cnv1-peer-engine-head' in MIHOMO\n    assert 'cnv1-engine-logo mihomo' in MIHOMO\n    assert 'cnv1-compact-protocols cnv1-engine-card sg-ljd-card sg-ui-card sg-ui-section' in TEMPLATE\n    assert 'AmneziaWG 3.1 · NaiveProxy' in TEMPLATE\n    assert '2 протокола' in TEMPLATE\n    assert '/* Unified engine shells: Xray, Mihomo and AWG31/NaiveProxy share one outer-card language. */' in CSS\n'''
test.write_text(checks, encoding="utf-8")
