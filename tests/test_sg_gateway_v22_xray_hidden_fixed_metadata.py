from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _controls_css() -> str:
    source = (ROOT / "app/web/static/sg-xmux-settings-v1.css").read_text(
        encoding="utf-8"
    )
    return source.split(
        "SG-Gateway 022.04 · Connections controls-only polish", 1
    )[1]


def _rule(source: str, selector: str) -> str:
    start = source.index(selector)
    end = source.index("}", start)
    return source[start : end + 1]


def test_xray_fixed_listener_metadata_is_not_rendered() -> None:
    template = (ROOT / "app/web/templates/connections.html").read_text(
        encoding="utf-8"
    )

    assert "xps2-field-port" not in template
    assert "xps2-system-port" not in template
    assert "<output>{{ profile.port }}</output>" not in template
    assert "Системный порт SG-Gateway" not in template
    assert 'name="{{ profile.id }}_port"' not in template


def test_only_profiles_with_real_controls_get_parameter_rows() -> None:
    template = (ROOT / "app/web/templates/connections.html").read_text(
        encoding="utf-8"
    )

    assert "{% if profile.id in ['xhttp_tls', 'hysteria2'] %}" in template
    assert "XHTTP mode клиента" in template
    assert 'name="hysteria2_obfs_mode"' in template


def test_xray_parameter_grids_do_not_reserve_a_port_column() -> None:
    css = _controls_css()

    assert ".xps2-field-port" not in css
    assert 'data-profile-panel="reality_tcp"' not in css
    assert 'data-profile-panel="xhttp_reality"' not in css

    xhttp_tls = _rule(
        css, '.xps2-parameter-row[data-profile-panel="xhttp_tls"] {'
    )
    assert 'grid-template-areas: "title mode";' in xhttp_tls
    assert "port" not in xhttp_tls

    hysteria2 = _rule(
        css, '.xps2-parameter-row[data-profile-panel="hysteria2"] {'
    )
    assert '"title"' in hysteria2
    assert '"obfs"' in hysteria2
    assert "port" not in hysteria2


def test_system_port_presentation_styles_are_removed() -> None:
    css = (ROOT / "app/web/static/sg-xray-profiles-v2.css").read_text(
        encoding="utf-8"
    )

    assert ".xps2-system-port" not in css
