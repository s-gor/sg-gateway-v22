from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "app/web/templates/_mihomo_panel.html"


def test_mihomo_service_actions_are_not_exposed_in_panel() -> None:
    source = TEMPLATE.read_text(encoding="utf-8")

    assert 'class="mhv2-service-tools"' not in source
    assert "Сервисные действия" not in source
    assert 'name="action" value="restart"' not in source
    assert "Перезапустить Mihomo" not in source
    assert "Только для уже применённой конфигурации." not in source

    assert 'name="action" value="save"' in source
    assert 'name="action" value="test"' in source
    assert 'name="action" value="apply"' in source


def test_mihomo_listener_runtime_statuses_are_preserved() -> None:
    source = TEMPLATE.read_text(encoding="utf-8")

    assert source.count("data-runtime-switch") >= 3
    assert "mieru_state.state_label" in source
    assert "anytls_state.state_label" in source
    assert "tuic_state.state_label" in source
