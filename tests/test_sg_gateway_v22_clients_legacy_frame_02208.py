from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
FRAME = ROOT / "app/web/static/sg-page-frame-routing-v1.css"

def test_02208_clients_no_longer_belong_to_legacy_routing_page_frame():
    css = FRAME.read_text(encoding="utf-8")
    assert ".cv2-page" not in css
    assert ".dv16-page" not in css
    for selector in ("dv16-heading", "dv16-heading-actions", "dv16-devices"):
        assert re.search(rf"(?m)^\s*\.{selector}\s*\{{", css) is None, selector
    for prelude in re.findall(r"([^{}]+)\{", css):
        candidate = prelude.strip()
        if candidate.startswith(":is(") and candidate.count(":is(") == 1 and candidate.endswith(")"):
            assert ".cv2-heading.cv15-heading" not in candidate, candidate
