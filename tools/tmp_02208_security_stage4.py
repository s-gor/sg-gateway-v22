from __future__ import annotations

import re
from pathlib import Path


BASE_SHA = "2968c31fe2376437059f703d6585cfdb180f39f6"


def _replace_once(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    if old not in text:
        raise RuntimeError(f"marker not found in {path}: {old[:140]!r}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


def write_tests() -> None:
    Path("tests/test_sg_gateway_v22_security_contract_02208.py").write_text(r'''from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SECURITY = (ROOT / "app/web/templates/security.html").read_text(encoding="utf-8")
SECURITY_CSS = (ROOT / "app/web/static/sg-security-v2.css").read_text(encoding="utf-8")
PASSWORD_CSS = (ROOT / "app/web/static/sg-security-password-fix1.css").read_text(encoding="utf-8")
FRAME = (ROOT / "app/web/static/sg-page-frame-routing-v1.css").read_text(encoding="utf-8")
PAGE_CSS = ROOT / "app/web/static/sg-ui-security-v22-08.css"


def test_02208_security_owns_page_assets_and_preserves_form_contracts() -> None:
    assert "{% block page_styles %}" in SECURITY
    assert "{% block head %}" not in SECURITY
    for asset in (
        "static_asset('sg-security-v2.css')",
        "static_asset('sg-security-password-fix1.css')",
        "static_asset('sg-ui-security-v22-08.css')",
    ):
        assert asset in SECURITY

    assert 'data-sg-ui-page="security"' in SECURITY
    for section in (
        "security-head",
        "security-summary",
        "security-tls",
        "security-password",
        "security-status",
        "security-tech",
        "security-footer",
    ):
        assert f'data-sg-section="{section}"' in SECURITY

    assert 'id="secv2-domain-input"' in SECURITY
    assert 'id="password-change"' in SECURITY
    for endpoint in (
        "security_tls_check",
        "security_tls_issue",
        "security_tls_renew",
        "security_tls_rollback",
        "security_password_change",
    ):
        assert f"url_for('{endpoint}')" in SECURITY

    for field in ("domain", "current_password", "new_password", "confirm_password"):
        assert f'name="{field}"' in SECURITY
    assert 'autocomplete="current-password"' in SECURITY
    assert SECURITY.count('autocomplete="new-password"') == 2
    assert SECURITY.count('minlength="8"') == 2
    assert SECURITY.count('method="post"') >= 5


def test_02208_security_legacy_styles_no_longer_own_outer_rails() -> None:
    assert not re.search(r"\.secv2-page\s*\{", SECURITY_CSS)
    assert not re.search(r"\.secv2-password-card\s*\{[^}]*margin-top", PASSWORD_CSS, re.S)
    for selector in (".secv2-page", ".ts2-page-heading", ".ts2-kicker", ".ts2-heading-actions"):
        assert selector not in FRAME

    assert PAGE_CSS.exists()
    page_css = PAGE_CSS.read_text(encoding="utf-8")
    assert '[data-sg-ui-page="security"]' in page_css
    assert '.sg-ui-security-head' in page_css
    assert "margin-inline: 0" in page_css
''', encoding="utf-8")

    Path("tests/test_sg_gateway_v22_security_geometry_02208.py").write_text(r'''from __future__ import annotations

import math

from playwright.sync_api import sync_playwright

import app.main as main
from tests.ui.browser_harness import login_panel, rect, serve_app, set_theme

VIEWPORTS = (
    {"width": 1440, "height": 1000},
    {"width": 1024, "height": 900},
    {"width": 390, "height": 844},
)


def _setup_app(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("SG_GATEWAY_ADMIN_PASSWORD", "secret")
    monkeypatch.setenv("SG_GATEWAY_SECRET_KEY", "security-browser-secret")
    monkeypatch.setenv("SG_GATEWAY_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("SG_GATEWAY_LOG_DIR", str(tmp_path / "logs"))
    monkeypatch.setenv("SG_GATEWAY_PUBLIC_ADDRESS", "203.0.113.10")
    monkeypatch.setenv("SG_GATEWAY_COUNTRY_CODE", "fr")
    monkeypatch.setattr(main, "password_is_default", lambda: False)
    monkeypatch.setattr(main, "security_tls_overview", lambda: {
        "domain": "panel.example.com",
        "https_ready": False,
        "public_url": "",
        "dns": None,
        "certificate": None,
        "certbot_timer_enabled": False,
        "nginx_active": False,
        "public_port": 443,
        "backend_port": 8080,
        "backups": [],
        "nginx_config": "/etc/nginx/sites-enabled/sg-gateway",
        "certificate_path": None,
        "last_message": "",
    })
    return main.create_app()


def _close(a: float, b: float, tolerance: float = 1.0) -> None:
    assert math.isclose(a, b, abs_tol=tolerance), (a, b)


def _same_rail(page, selectors):
    geometry = {selector: rect(page, selector) for selector in selectors}
    root = geometry[selectors[0]]
    for selector in selectors[1:]:
        _close(root["x"], geometry[selector]["x"])
        _close(root["width"], geometry[selector]["width"])
    return geometry


def test_02208_security_uses_canonical_rail_in_both_themes(tmp_path, monkeypatch):
    app = _setup_app(tmp_path, monkeypatch)
    selectors = (
        '[data-sg-ui-page="security"]',
        '[data-sg-section="security-head"]',
        '[data-sg-section="security-summary"]',
        '[data-sg-section="security-tls"]',
        '[data-sg-section="security-password"]',
        '[data-sg-section="security-status"]',
        '[data-sg-section="security-tech"]',
        '[data-sg-section="security-footer"]',
    )
    with serve_app(app) as base_url, sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        try:
            for viewport in VIEWPORTS:
                theme_geometry = {}
                for theme in ("dark", "light"):
                    page = browser.new_page(viewport=viewport)
                    login_panel(page, base_url, password="secret")
                    set_theme(page, theme)
                    page.goto(f"{base_url}/security", wait_until="networkidle")
                    assert page.evaluate(
                        "document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1"
                    )
                    geometry = _same_rail(page, selectors)
                    assert page.locator('#secv2-domain-input').is_visible()
                    assert page.locator('input[name="current_password"]').is_visible()
                    assert page.locator('input[name="new_password"]').is_visible()
                    assert page.locator('input[name="confirm_password"]').is_visible()
                    theme_geometry[theme] = geometry
                    page.close()
                for selector in selectors:
                    for key in ("x", "width"):
                        _close(theme_geometry["dark"][selector][key], theme_geometry["light"][selector][key])
        finally:
            browser.close()
''', encoding="utf-8")


def migrate_template() -> None:
    path = Path("app/web/templates/security.html")
    text = path.read_text(encoding="utf-8")
    old_head = '''{% block head %}\n<link rel="stylesheet" href="{{ url_for('static', filename='sg-security-v2.css') }}">\n<link rel="stylesheet" href="{{ url_for('static', filename='sg-security-password-fix1.css') }}">\n{% endblock %}'''
    new_head = '''{% block page_styles %}\n  <link rel="stylesheet" href="{{ static_asset('sg-security-v2.css') }}">\n  <link rel="stylesheet" href="{{ static_asset('sg-security-password-fix1.css') }}">\n  <link rel="stylesheet" href="{{ static_asset('sg-ui-security-v22-08.css') }}">\n{% endblock %}'''
    if old_head not in text:
        raise RuntimeError("Security legacy head block missing")
    text = text.replace(old_head, new_head, 1)

    replacements = {
        '<section class="secv2-page">': '<section class="secv2-page sg-ui-page sg-ui-security" data-sg-ui-page="security">',
        '<header class="ts2-page-heading">': '<header class="ts2-page-heading sg-ui-page-head sg-ui-security-head" data-sg-section="security-head">',
        '<div class="ts2-heading-actions">': '<div class="ts2-heading-actions sg-ui-actions">',
        '<section class="secv2-summary sg-ljd-strip">': '<section class="secv2-summary sg-ljd-strip" data-sg-section="security-summary">',
        '<article class="secv2-workflow sg-ljd-card-large">': '<article class="secv2-workflow sg-ljd-card-large" data-sg-section="security-tls">',
        '<article class="secv2-password-card sg-ljd-card-large" id="password-change">': '<article class="secv2-password-card sg-ljd-card-large" id="password-change" data-sg-section="security-password">',
        '<section class="secv2-lower-grid">': '<section class="secv2-lower-grid" data-sg-section="security-status">',
        '<details class="secv2-tech sg-ljd-card">': '<details class="secv2-tech sg-ljd-card" data-sg-section="security-tech">',
        '<footer class="secv2-footer">': '<footer class="secv2-footer" data-sg-section="security-footer">',
    }
    for old, new in replacements.items():
        if old not in text:
            raise RuntimeError(f"Security template marker missing: {old}")
        text = text.replace(old, new, 1)
    path.write_text(text, encoding="utf-8")


def migrate_security_css() -> None:
    path = Path("app/web/static/sg-security-v2.css")
    text = path.read_text(encoding="utf-8")
    old = '''.secv2-page {\n  display: grid;\n  gap: 17px;\n  min-width: 0;\n}\n\n'''
    if old not in text:
        raise RuntimeError("Security outer page CSS block missing")
    path.write_text(text.replace(old, "", 1), encoding="utf-8")


def migrate_password_css() -> None:
    path = Path("app/web/static/sg-security-password-fix1.css")
    text = path.read_text(encoding="utf-8")
    first = '''.secv2-password-card {\n  margin-top: 20px;\n}\n'''
    if first not in text:
        raise RuntimeError("Security password margin block missing")
    text = text.replace(first, "", 1)
    second = "  margin-top: 18px !important;\n"
    if second not in text:
        raise RuntimeError("Security password override margin missing")
    path.write_text(text.replace(second, "", 1), encoding="utf-8")


def migrate_legacy_frame() -> None:
    path = Path("app/web/static/sg-page-frame-routing-v1.css")
    text = path.read_text(encoding="utf-8")
    for token in (", .secv2-page", ", .ts2-page-heading", ", .ts2-kicker", ", .ts2-heading-actions"):
        if token not in text:
            raise RuntimeError(f"Security legacy frame selector missing: {token}")
        text = text.replace(token, "")

    before = text
    text = re.sub(
        r"\n\.ts2-kicker::before\s*\{.*?\}\n",
        "\n",
        text,
        count=1,
        flags=re.S,
    )
    if text == before:
        raise RuntimeError("Security ts2 kicker pseudo-element block missing")
    path.write_text(text, encoding="utf-8")


def write_page_css() -> None:
    Path("app/web/static/sg-ui-security-v22-08.css").write_text(r'''/* SG-Gateway 22.08 Security page ownership. Shared layout owns horizontal rails. */
[data-sg-ui-page="security"] {
  width: 100%;
  max-width: none;
  min-width: 0;
  margin: 0;
  padding: 0;
}

[data-sg-ui-page="security"] > .sg-ui-page-head,
[data-sg-ui-page="security"] > [data-sg-section] {
  box-sizing: border-box;
  width: 100%;
  max-width: none;
  min-width: 0;
  margin-inline: 0;
}

.sg-ui-security-head {
  min-height: 68px;
  padding-block: 4px 10px;
  border-bottom: 1px solid var(--sg-ui-border);
}

.sg-ui-security-head > div:first-child {
  min-width: 0;
}

.sg-ui-security-head h1 {
  font-size: 27px;
  line-height: 1.05;
}

.sg-ui-security-head .sg-ui-actions {
  min-width: 0;
}

@media (max-width: 760px) {
  .sg-ui-security-head {
    min-height: 0;
  }

  .sg-ui-security-head .sg-ui-actions {
    width: 100%;
  }
}
''', encoding="utf-8")


def migrate() -> None:
    migrate_template()
    migrate_security_css()
    migrate_password_css()
    migrate_legacy_frame()
    write_page_css()
