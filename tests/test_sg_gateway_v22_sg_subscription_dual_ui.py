from __future__ import annotations

import importlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DETAIL = ROOT / "app" / "web" / "templates" / "client_detail.html"
PARTIAL = ROOT / "app" / "web" / "templates" / "_sg_subscription_dual.html"
CSS = ROOT / "app" / "web" / "static" / "sg-subscription-verified-v1.css"
PATCHER = ROOT / "deploy" / "sg-gateway-sg-subscription-native-ui.sh"


def test_dual_ui_is_source_native_exactly_once_before_devices() -> None:
    text = DETAIL.read_text(encoding="utf-8")
    marker = "<!-- SG_SUBSCRIPTION_DUAL_UI_V1 -->"
    include = '{% include "_sg_subscription_dual.html" %}'
    devices = '<section class="dv16-devices" aria-label="Устройства клиента">'
    assert text.count(marker) == 1
    assert text.count(include) == 1
    assert text.index(marker) < text.index(include) < text.index(devices)
    assert "<strong>Подписка устройства</strong>" not in text
    assert text.count("<strong>OpenWrt · HomeProxy SUB</strong>") == 1
    assert text.count("<span>Подписка устройства для HomeProxy-совместимых клиентов.</span>") == 1
    assert "Ссылка для NekoBox и совместимых клиентов." not in text
    assert not PATCHER.exists()


def test_final_dual_partial_uses_explicit_v4_contract_without_awg3() -> None:
    text = PARTIAL.read_text(encoding="utf-8")
    assert "sg_subscription_universal_url(client)" in text
    assert "sg_subscription_native_url(client)" in text
    assert 'data-sg-subscription-format="universal"' in text
    assert 'data-sg-subscription-format="native"' in text
    assert 'class="button primary dv16-copy sg-subscription-copy-universal"' in text
    assert 'class="button dv16-copy sg-subscription-copy-native"' in text
    assert 'src="/clients/{{ client.id }}/sg-subscription-v1/qr/universal"' in text
    assert 'src="/clients/{{ client.id }}/sg-subscription-v1/qr"' in text
    assert "url_for('sg_subscription_v1" not in text
    assert "AWG2." in text
    for forbidden in ("AWG3", "amneziawg3", "AmneziaWG 3.0", "AWG2/AWG3"):
        assert forbidden not in text


def test_final_dual_css_keeps_distinct_actions_and_responsive_layout() -> None:
    text = CSS.read_text(encoding="utf-8")
    assert '.sg-subscription-format[data-sg-subscription-format="universal"]' in text
    assert '.sg-subscription-format[data-sg-subscription-format="native"]' in text
    assert ".sg-subscription-copy-universal" in text
    assert "var(--sg-ok" in text
    assert ".sg-subscription-copy-native" in text
    assert "var(--sg-blue" in text
    assert "@media (max-width: 760px)" in text
    assert "grid-template-columns: 1fr;" in text


def test_production_jinja_compiles_source_native_dual_partial(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("SG_GATEWAY_DATA_DIR", str(tmp_path / "data"))
    sys.modules.pop("app.production", None)
    production = importlib.import_module("app.production")
    production.app.jinja_env.get_template("client_detail.html")
    production.app.jinja_env.get_template("_sg_subscription_dual.html")
