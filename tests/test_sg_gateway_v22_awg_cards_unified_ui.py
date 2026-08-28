from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_awg31_endpoint_uses_the_same_flag_and_country_layout_as_other_awg_cards() -> None:
    panel = _read("app/web/templates/_awg31_panel.html")

    assert '<img src="{{ country_flag_url(awg3_country) }}"' in panel
    assert "{{ country_name(awg3_country) }}" in panel
    assert "интерфейс awg31" not in panel
    assert "10.131.0.0/24" not in panel


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
    assert "awgd-v31-service" not in panel
    assert "/connections/amneziawg31/service/" not in panel
    assert ".page-connections .awgd-card-v31 { grid-column: 1 / -1; }" not in stylesheet
