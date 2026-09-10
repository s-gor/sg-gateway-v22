from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LAYOUT = ROOT / "app/web/static/sg-ui-layout-v22-08.css"
CONNECTIONS = ROOT / "app/web/static/sg-ui-connections-v22-08.css"


def test_internal_service_address_is_hidden_from_user_facing_server_identity():
    css = LAYOUT.read_text(encoding="utf-8")
    for selector in (
        ".sg-brand-note",
        ".sg-server-meta > span:last-child",
        ".sg-current-value > span",
        ".cv2-server-cell small",
    ):
        assert selector in css
    assert "display: none !important;" in css


def test_xray_pinned_version_caption_is_not_user_visible():
    css = CONNECTIONS.read_text(encoding="utf-8")
    assert ".xps2-version-stack > small" in css
    assert "display: none !important;" in css


def test_mihomo_three_card_row_is_full_width_equal_and_stretched():
    css = CONNECTIONS.read_text(encoding="utf-8")
    assert "body.page-connections .cnv1-engine-xray .mhv2-inner-rail.sg-ui-rail" in css
    assert "padding-inline: 0;" in css
    assert "body.page-connections .mhv2-listeners" in css
    assert "grid-template-columns: repeat(3, minmax(0, 1fr));" in css
    assert "align-items: stretch;" in css
    assert "body.page-connections .mhv2-listener" in css
    assert "height: 100%;" in css
    assert "width: calc(100% + 36px);" not in css
    assert "margin-inline: -18px;" not in css
