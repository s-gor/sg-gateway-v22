from __future__ import annotations
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOGIN = (ROOT / "app/web/templates/login.html").read_text(encoding="utf-8")
RECOVERY = (ROOT / "app/web/templates/recovery.html").read_text(encoding="utf-8")


def _canonical(template: str) -> None:
    for asset in ("sg-ui-foundation-v22-08.css", "sg-ui-components-v22-08.css", "sg-ui-standalone-v22-08.css"):
        assert f"static_asset('{asset}')" in template, asset
    for legacy in ("app.css", "sg-luxury-jade-depth-v2.css", "sg-readable-typography-v3.css"):
        assert legacy not in template, legacy
    assert "?v=" not in template


def test_02208_login_is_standalone_and_preserves_form_contract() -> None:
    _canonical(LOGIN)
    assert 'data-sg-standalone-page="login"' in LOGIN
    assert '<form class="settings-form sg-ui-standalone-form" method="post" action="/login">' in LOGIN
    assert 'name="next" value="{{ next_url }}"' in LOGIN
    assert 'name="password" type="password" autocomplete="current-password" autofocus required' in LOGIN
    assert 'type="submit"' in LOGIN
    assert 'sg-ui-button' in LOGIN


def test_02208_recovery_is_standalone_and_preserves_restore_contract() -> None:
    _canonical(RECOVERY)
    assert "static_asset('sg-recovery-restore-v1.css')" in RECOVERY
    assert 'data-sg-standalone-page="recovery"' in RECOVERY
    for marker in ('id="recovery-confirm"', 'id="recovery-restore-form"', 'id="recovery-confirm-cancel"', 'data-recovery-restore', 'data-backup-name=', 'data-restore-url=', 'requestedRestore = {{ requested_restore|tojson }}'):
        assert marker in RECOVERY, marker
    assert "url_for('download_backup_route', name=backup.name)" in RECOVERY
    assert "url_for('recovery_restore_backup_route', name=backup.name)" in RECOVERY
    for href in ('href="/maintenance"', 'href="/maintenance/diagnostics.json"', 'href="/"'):
        assert href in RECOVERY
    assert 'recovery-restore-button sg-ui-button' in RECOVERY
