from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
NAIVE = ROOT / "app/naiveproxy/http.py"
CSS = ROOT / "app/web/static/sg-compact-protocol-cards-v1.css"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_naiveproxy_is_compact_third_card_without_visible_port_or_runtime_clutter() -> None:
    naive = _read(NAIVE)

    assert '<article id="sg-naiveproxy-settings"' in naive
    assert 'class="xps2-parameter-row is-visible xps2-naiveproxy-card"' in naive
    assert "HTTPS Forward Proxy · TLS" in naive
    assert "data-naive-host" in naive
    assert "data-naive-port" not in naive
    assert "data-naive-runtime" not in naive
    assert "TCP-порт NaiveProxy" not in naive
    assert "const parameterList = document.querySelector('.xps2-parameter-list');" in naive
    assert "parameterList.appendChild(root);" in naive
    assert "let activePort = 8447;" in naive
    assert "activePort = Number(payload.port || payload.default_port || 8447);" in naive
    assert "body: JSON.stringify({port: Number(activePort)})" in naive
    assert "healthy ? 'Работает' : 'Не настроен'" in naive
    assert "data-naive-submit" in naive
    assert "data-naive-form" not in naive
    assert "TCP {configured_port}" not in naive
    assert "sg-compact-protocol-cards-v1.css" in naive


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
