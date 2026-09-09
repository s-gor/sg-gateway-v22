from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CSS_PATH = ROOT / "app/web/static/sg-ui-connections-v22-08.css"
TEST_PATH = ROOT / "tests/test_sg_gateway_v22_awg31_naiveproxy_compact_ui_02208.py"

css = CSS_PATH.read_text(encoding="utf-8")
marker = "/* Unified protocol-card outline: match Xray profile cards */"
block = r'''

/* Unified protocol-card outline: match Xray profile cards */
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
if marker not in css:
    CSS_PATH.write_text(css.rstrip() + block + "\n", encoding="utf-8")

test = TEST_PATH.read_text(encoding="utf-8")
needle = "def test_mihomo_does_not_add_a_second_inner_rail() -> None:\n"
new_test = r'''

def test_mihomo_and_compact_protocol_cards_match_xray_outline() -> None:
    assert '/* Unified protocol-card outline: match Xray profile cards */' in CSS
    assert '.mhv2-listener,' in CSS
    assert '.cnv1-compact-protocol-card' in CSS
    assert 'border: 2px solid color-mix(' in CSS
    assert 'box-shadow:' in CSS
'''
if "test_mihomo_and_compact_protocol_cards_match_xray_outline" not in test:
    if needle in test:
        idx = test.index(needle)
        test = test[:idx] + new_test + "\n" + test[idx:]
    else:
        test = test.rstrip() + new_test + "\n"
    TEST_PATH.write_text(test, encoding="utf-8")
