from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CSS_PATH = ROOT / 'app/web/static/sg-ui-connections-v22-08.css'
NAIVE_PATH = ROOT / 'app/web/templates/_naiveproxy_panel.html'
TEST_PATH = ROOT / 'tests/test_sg_gateway_v22_awg31_naiveproxy_compact_ui_02208.py'

css = CSS_PATH.read_text(encoding='utf-8')
naive = NAIVE_PATH.read_text(encoding='utf-8')
test = TEST_PATH.read_text(encoding='utf-8')

old = '''/* Unified protocol-card outline: match Xray profile cards */
body.page-connections :is(
  .mhv2-listener,
  .cnv1-compact-protocol-card
) {
  border: 2px solid color-mix(in srgb, var(--sg-accent, #4f7d6c) 72%, var(--sg-ui-border, #aeb8ae));
  box-shadow:
    0 0 0 1px color-mix(in srgb, var(--sg-accent, #4f7d6c) 18%, transparent),
    0 8px 18px rgba(42, 60, 52, .14);
}
'''
new = '''/* Unified protocol-card shell: one visual language in light and dark themes */
body.page-connections :is(
  .mhv2-listener,
  .cnv1-compact-protocol-card
) {
  border: 2px solid color-mix(in srgb, var(--sg-accent, #4f7d6c) 72%, var(--sg-ui-border, #aeb8ae));
  border-radius: var(--sg-ui-nested-radius, 10px);
  background-clip: padding-box;
  box-shadow:
    0 0 0 1px color-mix(in srgb, var(--sg-accent, #4f7d6c) 18%, transparent),
    0 8px 18px rgba(42, 60, 52, .14);
}

body.page-connections :is(
  .mhv2-state,
  .cnv1-engine-status
) {
  min-height: var(--sg-ui-badge-height, 28px);
  padding-inline: 10px;
  border-radius: 999px;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  white-space: nowrap;
}
'''
if old not in css:
    raise SystemExit('outline block not found')
css = css.replace(old, new, 1)
css = css.replace("\nbody.page-connections .cnv1-compact-protocol-port {\n  position: absolute;\n  right: 14px;\n  bottom: 14px;\n  font-size: 11px;\n  opacity: .7;\n}\n", "\n")
css = css.replace("\n  body.page-connections .cnv1-compact-protocol-port { position: static; }", "")

naive = naive.replace('''  <div class="cnv1-compact-protocol-endpoint">\n    <span>HTTPS-домен</span>\n    <strong data-naive-host>—</strong>\n    <small data-naive-endpoint>Порт 8447 · требуется HTTPS в Security</small>\n  </div>''', '''  <div class="cnv1-compact-protocol-endpoint">\n    <span>HTTPS-домен</span>\n    <strong data-naive-host>—</strong>\n  </div>''')
naive = naive.replace('''  </div>\n  <span class="cnv1-compact-protocol-port" data-naive-port>8447/TCP</span>\n</article>''', '''  </div>\n</article>''')
naive = naive.replace("  const endpoint = root.querySelector('[data-naive-endpoint]');\n", "")
naive = naive.replace("  const portChip = root.querySelector('[data-naive-port]');\n", "")
naive = naive.replace("    if (host) host.textContent = domain || 'HTTPS не настроен';\n    if (endpoint) endpoint.textContent = domain\n      ? `${domain}:${activePort}`\n      : `Порт ${activePort} · требуется HTTPS в Security`;\n    if (portChip) portChip.textContent = `${activePort}/TCP`;\n", "    if (host) host.textContent = domain ? `${domain}:${activePort}` : 'HTTPS не настроен';\n")

if 'def test_protocol_cards_share_one_visual_shell_and_naive_has_no_duplicate_port()' not in test:
    test += '''\n\ndef test_protocol_cards_share_one_visual_shell_and_naive_has_no_duplicate_port() -> None:\n    assert 'border-radius: var(--sg-ui-nested-radius, 10px);' in CSS\n    assert 'background-clip: padding-box;' in CSS\n    assert 'cnv1-compact-protocol-port' not in CSS\n    assert 'data-naive-port' not in NAIVE\n    assert 'data-naive-endpoint' not in NAIVE\n    assert "`${domain}:${activePort}`" in NAIVE\n'''

CSS_PATH.write_text(css, encoding='utf-8')
NAIVE_PATH.write_text(naive, encoding='utf-8')
TEST_PATH.write_text(test, encoding='utf-8')
