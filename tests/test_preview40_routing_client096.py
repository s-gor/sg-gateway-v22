from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_routing_layout_is_ported_from_sg_client_096():
    template = (ROOT / "app/web/templates/routing.html").read_text(encoding="utf-8")
    for marker in (
        "Выбранная конфигурация",
        "Пользовательские правила",
        "Базовая схема",
        "Основные правила",
        "Российская маршрутизация",
        "Наборы geosite / geoip",
    ):
        assert marker in template
    assert 'data-r096-tab="routing"' in template
    assert 'data-r096-tab="geofiles"' in template


def test_routing_themes_match_current_sg_gateway_palettes():
    css = (ROOT / "app/web/static/sg-routing-client096.css").read_text(encoding="utf-8")
    for color in (
        "#0B121C",
        "#111D2B",
        "#7FB2E0",
        "#477AAA",
        "#315E8C",
        "#E5ECE7",
        "#F8F5EE",
        "#456F5C",
        "#B88A45",
    ):
        assert color in css


def test_geofiles_ui_and_sources_are_complete():
    template = (ROOT / "app/web/templates/_geofiles_panel.html").read_text(encoding="utf-8")
    source = (ROOT / "app/routing/geofiles.py").read_text(encoding="utf-8")
    for marker in ("Установленные файлы", "Источник GeoFiles", "Проверка и применение", "Вернуть комплектные"):
        assert marker in template
    for source_name in ("Loyalsoldier", "RunetFreedom", "RoscomVPN", "Встроенная пара SG Client"):
        assert source_name in source
    assert (ROOT / "assets/geofiles/geoip.dat").stat().st_size > 1_000_000
    assert (ROOT / "assets/geofiles/geosite.dat").stat().st_size > 1_000_000


def test_smart_routing_backend_is_wired():
    templates = (ROOT / "app/routing/templates.py").read_text(encoding="utf-8")
    main = (ROOT / "app/main.py").read_text(encoding="utf-8")
    assert "def stage_smart_routing" in templates
    assert "SMART_PRESET_TITLES" in templates
    assert '@app.post("/routing/smart/preview")' in main


def test_smart_routing_builds_real_candidate(tmp_path, monkeypatch):
    monkeypatch.setenv("SG_GATEWAY_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("SG_GATEWAY_LOG_DIR", str(tmp_path / "log"))
    monkeypatch.setenv("SG_GATEWAY_GEOFILES_STATE_DIR", str(tmp_path / "geo-state"))
    monkeypatch.setenv("SG_GATEWAY_XRAY_ASSET_DIR", str(ROOT / "assets/geofiles"))
    monkeypatch.setenv("SG_GATEWAY_ROUTING_STATE_DIR", str(tmp_path / "routing"))
    from app.db import init_db
    from app.routing.templates import stage_smart_routing
    init_db()
    candidate = stage_smart_routing(
        {
            "preset": "custom",
            "russia_scope": "sites_ip",
            "russia_action": "direct",
            "ads_action": "block",
            "default_action": "direct",
            "custom_direct_domains": "example.com",
            "custom_block_ips": "203.0.113.10",
        }
    )
    assert candidate["ready"] is True
    assert candidate["smart"]["preset"] == "custom"
    rules = candidate["managed_fragment"]["routing"]["rules"]
    assert rules
    assert {rule["outboundTag"] for rule in rules} <= {"direct", "block"}
    assert not any(rule.get("network") == "tcp,udp" for rule in rules)
    assert candidate["rules"][-1].get("implicit_default") is True
    assert any(rule["title"] == "Российская маршрутизация" for rule in candidate["rules"])
