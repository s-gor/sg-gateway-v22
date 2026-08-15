from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def source(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_device_cards_are_hidden_before_deferred_collapse_js_runs() -> None:
    css = source("app/web/static/sg-device-collapse-v1.css")
    js = source("app/web/static/sg-device-collapse-v1.js")

    assert "SG_GATEWAY_02112_CLIENTS_NO_JUMP_FIX4" in css
    assert (
        'body .dv16-device:not([data-sg-collapse-ready="1"]) > :not(.dv16-device-head)'
        in css
    )
    assert "display: none !important;" in css
    assert "card.dataset.sgCollapseReady = '1';" in js
    assert "setExpanded(card, button, false);" in js
