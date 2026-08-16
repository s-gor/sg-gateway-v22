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



def test_connections_protocol_cards_show_only_real_controls_as_fields():
    template = (ROOT / "app/web/templates/connections.html").read_text(encoding="utf-8")
    css = (ROOT / "app/web/static/sg-xmux-settings-v1.css").read_text(encoding="utf-8")
    polish = css.split("SG-Gateway 022.04 · Connections controls-only polish", 1)[1]
    assert "Здесь только то, что можно изменить" in template
    for field_class in ("xps2-field-port", "xps2-field-mode", "xps2-field-path"):
        assert field_class in template
    for meta in ("xps2-profile-meta", "Vision · {{ profile.flow }}", "XHTTP client · stream-one", "VLESS Encryption ·"):
        assert meta in template
    assert "Без дополнительного Path" not in template
    assert "Обязательный XTLS Vision для выбранного VLESS-профиля" not in template
    assert "Ключ клиента хранится в защищённых настройках" not in template
    assert ".xps2-profile-meta" in polish
    assert ".xps2-field-port" in polish
    assert ".xps2-field-mode" in polish
    assert ".xps2-field-path" in polish
    assert "display: none" not in polish


def test_reality_xhttp_fixed_mode_is_native_hidden_form_value_not_fake_control():
    template = (ROOT / "app/web/templates/connections.html").read_text(encoding="utf-8")
    js = (ROOT / "app/web/static/sg-xmux-settings-v1.js").read_text(encoding="utf-8")
    assert "{% if profile.id == 'xhttp_reality' %}" in template
    assert '<input type="hidden" name="{{ profile.id }}_mode" value="stream-one">' in template
    assert "data-xmux-reality-fixed" not in js
    assert "label.replaceWith" not in js
    assert "Reality XHTTP mode is rendered by the main form as a hidden stream-one" in js


def test_connections_protocol_cards_keep_all_mutable_form_contracts():
    template = (ROOT / "app/web/templates/connections.html").read_text(encoding="utf-8")
    for field in (
        'name="{{ profile.id }}_port"',
        'name="{{ profile.id }}_mode"',
        'name="{{ profile.id }}_path"',
        'name="hysteria2_obfs_mode"',
        'name="hysteria2_obfs_password"',
        'name="hysteria2_obfs_rotate"',
    ):
        assert field in template
    for value in ('value="none"', 'value="salamander"', 'value="gecko"'):
        assert value in template
    assert "Проверить конфигурацию" in template
    assert "Сохранить и применить" in template


def test_connections_protocol_cards_have_compact_profile_specific_grids():
    css = (ROOT / "app/web/static/sg-xmux-settings-v1.css").read_text(encoding="utf-8")
    polish = css.split("SG-Gateway 022.04 · Connections controls-only polish", 1)[1]
    for profile_id in ("reality_tcp", "xhttp_reality", "xhttp_tls", "hysteria2"):
        assert f'data-profile-panel="{profile_id}"' in polish
    assert 'grid-template-areas: "title port";' in polish
    assert 'grid-template-areas: "title port path";' in polish
    assert 'grid-template-areas: "title port mode path";' in polish
    assert '"obfs obfs"' in polish
    assert "box-shadow: none" in polish


def test_connections_protocol_cards_cover_low_resolution_and_mobile():
    css = (ROOT / "app/web/static/sg-xmux-settings-v1.css").read_text(encoding="utf-8")
    polish = css.split("SG-Gateway 022.04 · Connections controls-only polish", 1)[1]
    assert "@media (min-width: 981px) and (max-width: 1366px)" in polish
    assert "(min-width: 981px) and (max-height: 820px)" in polish
    assert "@media (max-width: 1050px)" in polish
    assert "@media (max-width: 760px)" in polish
    assert 'grid-template-areas: "title" "port" "mode" "path";' in polish
