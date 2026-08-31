from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "app/web/templates/connections.html"
STYLESHEET = ROOT / "app/web/static/sg-xray-profiles-v2.css"


def _css_block(source: str, selector: str) -> str:
    start = source.index(selector)
    end = source.index("}", start)
    return source[start : end + 1]


def test_hysteria2_password_action_uses_compact_label() -> None:
    source = TEMPLATE.read_text(encoding="utf-8")

    assert "data-salamander-generate>Новый пароль</button>" in source
    assert "Сгенерировать новый" not in source


def test_hysteria2_obfuscation_heading_and_modes_share_one_row() -> None:
    source = STYLESHEET.read_text(encoding="utf-8")
    panel_source = source[source.index("/* SG-Gateway 016"): ]
    panel = _css_block(panel_source, ".xps2-salamander {")
    heading = _css_block(source, ".xps2-salamander > header > div {")

    assert "grid-template-columns: auto minmax(0, 1fr)" in panel
    assert "gap: 10px 14px" in panel
    assert "padding: 12px 14px" in panel
    assert "display: flex" in heading
    assert "align-items: baseline" in heading
    assert "gap: 8px" in heading


def test_hysteria2_controls_are_dense_without_losing_actions() -> None:
    source = STYLESHEET.read_text(encoding="utf-8")
    mode_label = _css_block(source, ".xps2-salamander-modes label {")
    mode_chip = _css_block(source, ".xps2-salamander-modes span {")
    password = _css_block(source, '.xps2-salamander-secret input[type="password"],')
    buttons = _css_block(source, ".xps2-salamander-buttons .button {")
    status = _css_block(source, ".xps2-salamander-status {")

    assert "min-height: 34px" in mode_label
    assert "min-height: 34px" in mode_chip
    assert "min-height: 40px" in password
    assert "min-height: 40px" in buttons
    assert "grid-column: 1 / -1" in status
    assert "margin-top: -4px" in status


def test_hysteria2_mobile_keeps_field_and_actions_readable() -> None:
    source = STYLESHEET.read_text(encoding="utf-8")

    mobile = source.split("@media (max-width: 900px) {", 1)[1].split("@media (max-width: 650px)", 1)[0]
    assert ".xps2-salamander {" in mobile
    assert "grid-template-columns: 1fr" in mobile
    assert ".xps2-salamander-secret" in mobile
    assert ".xps2-salamander-buttons" in mobile
    assert "grid-template-columns: repeat(3, minmax(0, 1fr))" in mobile
