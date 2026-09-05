from __future__ import annotations

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
