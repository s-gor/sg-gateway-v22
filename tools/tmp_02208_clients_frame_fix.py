from __future__ import annotations

import re
from pathlib import Path

import tinycss2

FRAME = Path("app/web/static/sg-page-frame-routing-v1.css")
TEST = Path("tests/test_sg_gateway_v22_clients_legacy_frame_02208.py")


def _split_top_level_selectors(text: str) -> list[str]:
    out: list[str] = []
    start = 0
    depth = 0
    quote: str | None = None
    escaped = False
    for index, ch in enumerate(text):
        if quote is not None:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == quote:
                quote = None
            continue
        if ch in {"'", '"'}:
            quote = ch
            continue
        if ch in "([":
            depth += 1
        elif ch in ")]":
            depth = max(0, depth - 1)
        elif ch == "," and depth == 0:
            item = text[start:index].strip()
            if item:
                out.append(item)
            start = index + 1
    item = text[start:].strip()
    if item:
        out.append(item)
    return out


def _remove_cv2_page_arm(selector: str) -> str:
    selector = selector.replace(", .cv2-page", "")
    selector = selector.replace(".cv2-page, ", "")
    return selector


def _remove_exact_cv2_heading_arm(selector: str) -> str:
    stripped = selector.strip()
    if stripped.count(":is(") != 1 or not stripped.endswith(")"):
        return selector
    selector = selector.replace(", .cv2-heading.cv15-heading", "")
    selector = selector.replace(".cv2-heading.cv15-heading, ", "")
    return selector


def _filter_rule_prelude(prelude: str) -> str | None:
    selectors = _split_top_level_selectors(prelude)
    kept: list[str] = []
    for selector in selectors:
        exact = selector.strip()
        if exact in {".dv16-page", ".dv16-heading", ".dv16-heading-actions", ".dv16-devices"}:
            continue
        selector = _remove_cv2_page_arm(selector)
        selector = _remove_exact_cv2_heading_arm(selector)
        if ".cv2-page" in selector:
            raise RuntimeError(f"cv2 page ownership survived selector transform: {selector}")
        if selector.strip():
            kept.append(selector.strip())
    if not kept:
        return None
    return ",\n".join(kept)


def _filter_rules(nodes):
    result = []
    for node in nodes:
        if node.type == "qualified-rule":
            prelude = tinycss2.serialize(node.prelude).strip()
            filtered = _filter_rule_prelude(prelude)
            if filtered is None:
                continue
            if filtered != prelude:
                node.prelude = tinycss2.parse_component_value_list(filtered)
            result.append(node)
            continue
        if (
            node.type == "at-rule"
            and node.content is not None
            and node.lower_at_keyword in {"media", "supports", "layer", "container"}
        ):
            children = tinycss2.parse_rule_list(
                node.content,
                skip_whitespace=False,
                skip_comments=False,
            )
            filtered_children = _filter_rules(children)
            rendered = tinycss2.serialize(filtered_children)
            if not rendered.strip():
                continue
            node.content = tinycss2.parse_component_value_list(rendered)
            result.append(node)
            continue
        result.append(node)
    return result


def write_regression_test() -> None:
    TEST.write_text(
        '''from pathlib import Path\nimport re\n\nROOT = Path(__file__).resolve().parents[1]\nFRAME = ROOT / "app/web/static/sg-page-frame-routing-v1.css"\n\ndef test_02208_clients_no_longer_belong_to_legacy_routing_page_frame():\n    css = FRAME.read_text(encoding="utf-8")\n    assert ".cv2-page" not in css\n    assert ".dv16-page" not in css\n    for selector in ("dv16-heading", "dv16-heading-actions", "dv16-devices"):\n        assert re.search(rf"(?m)^\\s*\\.{selector}\\s*\\{{", css) is None, selector\n    assert re.search(r"(?s):is\\([^{}]*\\.cv2-heading\\.cv15-heading[^{}]*\\)\\s*\\{", css) is None\n''',
        encoding="utf-8",
    )


def migrate_legacy_frame() -> None:
    source = FRAME.read_text(encoding="utf-8")
    if ".cv2-page" not in source or ".dv16-page" not in source:
        raise RuntimeError("expected legacy Clients frame ownership is missing before migration")
    rules = tinycss2.parse_stylesheet(
        source,
        skip_whitespace=False,
        skip_comments=False,
    )
    cleaned = tinycss2.serialize(_filter_rules(rules))
    if ".cv2-page" in cleaned or ".dv16-page" in cleaned:
        raise RuntimeError("legacy Clients page ownership remained after migration")
    FRAME.write_text(cleaned, encoding="utf-8")


if __name__ == "__main__":
    write_regression_test()
    migrate_legacy_frame()
