from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_awg31_endpoint_uses_the_same_flag_and_country_layout_as_other_awg_cards() -> None:
    panel = _read("app/web/templates/_awg31_panel.html")

    assert '<img src="{{ country_flag_url(awg3_country) }}"' in panel
    assert "{{ country_name(awg3_country) }}" in panel
    assert 'class="awgd-v31-technical" hidden' in panel


def test_fixed_awg_ports_are_not_shown_as_editable_form_rows() -> None:
    panel = _read("app/web/templates/_awg31_panel.html")
    stylesheet = _read("app/web/static/sg-awg-dual-v1.css")

    assert "<span>UDP-порт</span>" not in panel
    for selector in (
        ".page-connections .awgd-card-v2 .cnv1-compact-fields > label:first-child",
        ".page-connections .awgd-card-v3 .cnv1-compact-fields > label:first-child",
    ):
        assert selector in stylesheet
    assert "display: none;" in stylesheet


def test_awg31_card_matches_shared_status_and_control_structure() -> None:
    panel = _read("app/web/templates/_awg31_panel.html")
    stylesheet = _read("app/web/static/sg-awg-dual-v1.css")

    assert "{% set awg31_ready =" in panel
    assert "'Настроено' if awg31_ready else 'Готов к первому запуску'" in panel
    assert '<details class="awgd-v31-service sg-ljd-nested" hidden>' in panel
    assert "/connections/amneziawg31/service/" in panel
    assert ".page-connections .awgd-card-v31 { grid-column: 1 / -1; }" not in stylesheet


def test_awg_shell_header_is_visibly_compact_without_persistent_divider() -> None:
    panel = _read("app/web/templates/_awg31_panel.html")
    stylesheet = _read("app/web/static/sg-awg-dual-v1.css")

    assert 'id="sg-awg-header-density-fix"' not in panel

    header_css = stylesheet.split(".page-connections .awgd-shell > .cnv1-engine-head {", 1)[1].split("}", 1)[0]
    assert "border-bottom: 0;" in header_css
    assert "padding: 10px 18px 4px;" in header_css
    assert "align-items: center;" in header_css

    grid_css = stylesheet.split(".page-connections .awgd-grid {", 1)[1].split("}", 1)[0]
    assert "padding: 4px 18px 18px;" in grid_css

    footer_css = stylesheet.split(".page-connections .awgd-footer {", 1)[1].split("}", 1)[0]
    assert "padding: 0;" in footer_css
    assert "align-self: center;" in footer_css

    assert ".page-connections .awgd-shell > .cnv1-engine-head .cnv1-engine-logo" in stylesheet
    assert "width: 38px;" in stylesheet
    assert "height: 38px;" in stylesheet
