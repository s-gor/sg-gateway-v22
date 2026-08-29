from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "app/web/templates/_mihomo_panel.html"


def _service_tools_fragment() -> str:
    source = TEMPLATE.read_text(encoding="utf-8")
    marker = 'class="mhv2-service-tools"'
    start = source.index(marker)
    return source[max(0, start - 40) : start + 700]


def test_mihomo_service_action_is_always_visible_without_accordion() -> None:
    fragment = _service_tools_fragment()

    assert "<details" not in fragment
    assert "<summary" not in fragment
    assert "Сервисные действия" in fragment
    assert 'name="action" value="restart"' in fragment
    assert "Перезапустить Mihomo" in fragment
    assert "Только для уже применённой конфигурации." in fragment


def test_mihomo_listener_runtime_statuses_are_preserved() -> None:
    source = TEMPLATE.read_text(encoding="utf-8")

    assert source.count("data-runtime-switch") >= 3
    assert "mieru_state.state_label" in source
    assert "anytls_state.state_label" in source
    assert "tuic_state.state_label" in source
