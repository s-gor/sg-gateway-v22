from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_connections_visual_v1_uses_existing_context():
    template = (ROOT / "app/web/templates/connections.html").read_text(encoding="utf-8")
    for marker in (
        "connections",
        "awg_settings",
        "xray_settings",
        "xray_profiles",
        "country_name",
        "country_flag_url",
    ):
        assert marker in template


def test_connections_visual_v1_uses_existing_post_routes():
    template = (ROOT / "app/web/templates/connections.html").read_text(encoding="utf-8")
    assert "url_for('update_amneziawg')" in template
    assert "url_for('update_xray')" in template
    assert "url_for('update_xray_profiles')" in template
    assert 'name="host"' in template
    assert 'name="port"' in template
    assert 'name="dns"' in template
    assert 'name="server_public_key"' in template
    assert 'name="server_name"' in template
    assert 'name="public_key"' in template
    assert 'name="short_id"' in template


def test_connections_visual_v1_has_reference_layout():
    template = (ROOT / "app/web/templates/connections.html").read_text(encoding="utf-8")
    for marker in (
        "cnv1-engine-pair",
        "cnv1-engine-awg",
        "cnv1-engine-xray",
        "cnv1-engine-wide",
        "cnv1-note-panel",
    ):
        assert marker in template
    assert "cnv1-map-panel" not in template
    assert template.index("cnv1-engine-xray") < template.index("cnv1-engine-awg")
    assert template.index("cnv1-engine-awg") < template.index('_mihomo_panel.html')


def test_xray_profiles_follow_choose_check_apply_flow():
    template = (ROOT / "app/web/templates/connections.html").read_text(encoding="utf-8")
    css = (ROOT / "app/web/static/sg-xray-profiles-v2.css").read_text(encoding="utf-8")
    for marker in (
        "xps2-choice-grid",
        "xps2-selector",
        "Выбрано, ещё не применено",
        "Проверить конфигурацию",
        "Сохранить и применить",
        'name="action" value="test"',
        'name="action" value="apply"',
        "data-profile-panel",
    ):
        assert marker in template
    for removed in (
        "ЭТАП 1",
        "Сохранить Xray-профили",
        "Проверка и атомарное применение",
        "Открыть терминал и применить",
    ):
        assert removed not in template
    assert ".xps2-choice-grid" in css
    assert ".xps2-parameter-row.is-visible" in css


def test_connections_summary_row_is_removed():
    template = (ROOT / "app/web/templates/connections.html").read_text(encoding="utf-8")
    assert 'class="cnv1-summary sg-ljd-strip"' not in template
    for label in ("Движки", "Активные listener", "Внешние порты"):
        assert label not in template


def test_connections_visual_v1_does_not_claim_automatic_apply_on_choice():
    template = (ROOT / "app/web/templates/connections.html").read_text(encoding="utf-8")
    assert "Простое нажатие ничего не применяет" in template
    for forbidden in (
        "Перезапустить Xray",
        "Перезапустить AmneziaWG",
        "Проверка порта успешна",
        "Live traffic",
    ):
        assert forbidden not in template


def test_connections_visual_v1_css_exists():
    path = ROOT / "app/web/static/sg-connections-visual-v1.css"
    assert path.is_file()
    css = path.read_text(encoding="utf-8")
    assert ".cnv1-engines" in css
    assert ".cnv1-engine-card" in css
    final = (ROOT / "app/web/static/sg-preview28-final.css").read_text(encoding="utf-8")
    assert ".cnv1-engine-pair" in final
    assert "grid-template-columns: minmax(0, 1fr) minmax(0, 1fr)" in final
