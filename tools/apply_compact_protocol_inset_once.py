from pathlib import Path
import hashlib

ROOT = Path(__file__).resolve().parents[1]
css_path = ROOT / "app/web/static/sg-ui-connections-v22-08.css"
test_path = ROOT / "tests/test_sg_gateway_v22_awg31_naiveproxy_compact_ui_02208.py"
source_path = ROOT / "SOURCE-SHA256SUMS"

css = css_path.read_text(encoding="utf-8")
old = "body.page-connections .cnv1-compact-protocols .sg-ui-rail {\n  padding-inline: var(--sg-ui-rail-inset, 18px);\n}"
new = "body.page-connections .cnv1-compact-protocols .sg-ui-rail {\n  padding-inline: calc(var(--sg-ui-card-pad, 18px) + var(--sg-ui-rail-inset, 18px));\n}"
assert old in css, "compact rail rule not found"
css = css.replace(old, new, 1)
mobile_marker = "@media (max-width: 620px) {\n  body.page-connections .cnv1-compact-protocol-head"
mobile_rule = "@media (max-width: 620px) {\n  body.page-connections .cnv1-compact-protocols .sg-ui-rail { padding-inline: var(--sg-ui-rail-inset, 14px); }\n  body.page-connections .cnv1-compact-protocol-head"
assert mobile_marker in css, "mobile marker not found"
css = css.replace(mobile_marker, mobile_rule, 1)
css_path.write_text(css, encoding="utf-8")

test = test_path.read_text(encoding="utf-8")
needle = "    assert 'grid-template-columns: repeat(2, minmax(0, 1fr));' in CSS\n"
addition = needle + "    assert 'padding-inline: calc(var(--sg-ui-card-pad, 18px) + var(--sg-ui-rail-inset, 18px));' in CSS\n"
assert needle in test, "test anchor not found"
test = test.replace(needle, addition, 1)
test_path.write_text(test, encoding="utf-8")

lines = source_path.read_text(encoding="utf-8").splitlines()
tracked = {"app/web/static/sg-ui-connections-v22-08.css", "tests/test_sg_gateway_v22_awg31_naiveproxy_compact_ui_02208.py"}
out = []
for line in lines:
    if "  " not in line:
        out.append(line)
        continue
    _, path = line.split("  ", 1)
    if path in tracked:
        digest = hashlib.sha256((ROOT / path).read_bytes()).hexdigest()
        out.append(f"{digest}  {path}")
    else:
        out.append(line)
source_path.write_text("\n".join(out) + "\n", encoding="utf-8")

# One-shot helper removes itself after applying.
Path(__file__).unlink()
