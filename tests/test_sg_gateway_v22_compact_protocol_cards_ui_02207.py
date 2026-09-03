from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "app/web/templates/connections.html"
NAIVE = ROOT / "app/naiveproxy/http.py"
CSS = ROOT / "app/web/static/sg-xray-profiles-v2.css"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_naiveproxy_is_compact_third_card_without_visible_port_or_runtime_clutter() -> None:
    template = _read(TEMPLATE)
    naive = _read(NAIVE)

    assert "<!-- SG_NAIVEPROXY_COMPACT_CARD -->" in template
    assert '<article id="sg-naiveproxy-settings"' in naive
    assert 'class="xps2-parameter-row is-visible xps2-naiveproxy-card"' in naive
    assert "HTTPS Forward Proxy · TLS" in naive
    assert "data-naive-host" in naive
    assert "data-naive-port" not in naive
    assert "data-naive-runtime" not in naive
    assert "TCP-порт NaiveProxy" not in naive
    assert "let activePort = 8447;" in naive
    assert "activePort = Number(payload.port || payload.default_port || 8447);" in naive
    assert "body: JSON.stringify({port: Number(activePort)})" in naive
    assert "healthy ? 'Работает' : 'Не настроен'" in naive
    assert "body.replace(naive_marker, _SETTINGS_PANEL, 1)" in naive
    assert "TCP {configured_port}" not in naive


def test_hysteria2_has_effective_compact_overrides() -> None:
    css = _read(CSS)
    marker = "/* SG-Gateway 022.07 · compact protocol cards */"

    assert marker in css
    compact = css.split(marker, 1)[1]
    assert '.xps2-parameter-row[data-profile-panel="hysteria2"] .xps2-salamander {' in compact
    assert "gap: 8px 10px;" in compact
    assert "padding: 9px 11px;" in compact
    assert "min-height: 30px;" in compact
    assert "min-height: 34px;" in compact
    assert ".xps2-naiveproxy-card" in compact
    assert ".xps2-naiveproxy-meta" in compact
    assert ".xps2-naiveproxy-action" in compact


def test_light_client_fingerprint_has_explicit_high_contrast_surface() -> None:
    css = _read(CSS)
    marker = "/* SG-Gateway 022.07 · compact protocol cards */"

    assert marker in css
    compact = css.split(marker, 1)[1]
    assert 'html[data-theme="light"] body.page-connections .xps2-parameter-row[data-fingerprint-panel]' in compact
    assert "border-color: #7f96a5;" in compact
    assert "background: #f2f5f7;" in compact
    assert "color: #172531;" in compact
    assert "color: #455d6b;" in compact
