from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
NAIVE = ROOT / "app/web/templates/_naiveproxy_panel.html"
CONNECTIONS = ROOT / "app/web/templates/connections.html"
CSS = ROOT / "app/web/static/sg-compact-protocol-cards-v1.css"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_naiveproxy_is_native_bottom_engine_card() -> None:
    naive = _read(NAIVE)
    connections = _read(CONNECTIONS)

    assert '<article id="sg-naiveproxy-settings"' in naive
    assert "xps2-naiveproxy-card" in naive
    assert "HTTPS FORWARD PROXY · TLS" in naive
    assert "data-naive-host" in naive
    assert "data-naive-port" in naive
    assert "data-naive-runtime" not in naive
    assert "data-naive-submit" in naive
    assert "let activePort = 8447;" in naive
    assert "activePort = Number(payload.port || payload.default_port || 8447);" in naive
    assert "body: JSON.stringify({port: Number(activePort)})" in naive
    assert "healthy ? 'Работает' : 'Не настроен'" in naive
    assert connections.count('{% include "_naiveproxy_panel.html" %}') == 1
    assert connections.index('_naiveproxy_panel.html') < connections.index("cnv1-note-panel")


def test_hysteria2_has_effective_compact_overrides() -> None:
    css = _read(CSS)
    marker = "/* SG-Gateway 022.07 · compact protocol cards */"

    assert marker in css
    assert '.xps2-parameter-row[data-profile-panel="hysteria2"] .xps2-salamander {' in css
    assert "gap: 8px 10px;" in css
    assert "padding: 9px 11px;" in css
    assert "min-height: 30px;" in css
    assert "min-height: 34px;" in css
    assert ".xps2-naiveproxy-card" in css
    assert ".xps2-naiveproxy-meta" in css
    assert ".xps2-naiveproxy-action" in css


def test_light_client_fingerprint_has_explicit_high_contrast_surface() -> None:
    css = _read(CSS)

    assert 'html[data-theme="light"] body.page-connections .xps2-parameter-row[data-fingerprint-panel]' in css
    assert "border-color: #7f96a5;" in css
    assert "background: #f2f5f7;" in css
    assert "color: #172531;" in css
    assert "color: #455d6b;" in css
