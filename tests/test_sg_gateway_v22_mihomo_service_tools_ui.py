from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "app/web/templates/_mihomo_panel.html"


def test_mihomo_restart_is_visible_without_service_actions_disclosure() -> None:
    source = TEMPLATE.read_text(encoding="utf-8")

    assert 'class="mhv2-service-tools"' not in source
    assert "Сервисные действия" not in source
    assert "<summary>Перезапуск" not in source
    assert 'class="mhv2-restart-row"' in source
    assert 'name="action" value="restart">Перезапустить</button>' in source
    assert "Перезапустить Mihomo" not in source
    assert "Только для уже применённой конфигурации." in source

    assert 'name="action" value="save"' in source
    assert 'name="action" value="test"' in source
    assert 'name="action" value="apply"' in source


def test_mihomo_listener_runtime_statuses_are_preserved() -> None:
    source = TEMPLATE.read_text(encoding="utf-8")

    assert source.count("data-runtime-switch") >= 3
    assert "mieru_state.state_label" in source
    assert "anytls_state.state_label" in source
    assert "tuic_state.state_label" in source
    assert "mihomo.listener_active" in source
    assert "mihomo.listener_total" in source


def test_mihomo_compact_spacing_contract() -> None:
    source = TEMPLATE.read_text(encoding="utf-8")

    assert "#mihomo .mhv2-compact-meta" in source
    assert "gap: 8px;" in source
    assert "margin-bottom: 6px;" in source
    assert "#mihomo .mhv2-form-compact" in source
    assert "gap: 10px;" in source
    assert "justify-content: flex-start;" in source
