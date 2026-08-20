from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "app" / "web" / "templates" / "base.html"
MAINTENANCE = ROOT / "app" / "web" / "templates" / "maintenance.html"
SCRIPT = ROOT / "app" / "web" / "static" / "sg-maintenance-recovery-v1.js"


def test_full_restore_verifies_then_starts_restore_without_second_manual_click():
    base = BASE.read_text(encoding="utf-8")
    maintenance = MAINTENANCE.read_text(encoding="utf-8")
    script = SCRIPT.read_text(encoding="utf-8")

    assert "sg-maintenance-recovery-v1.js" in base
    assert "active_page|default('') == 'maintenance'" in base
    assert "url_for('restore_full_backup_route')" in maintenance
    assert 'name="backup_action" value="verify"' in maintenance
    assert 'name="backup_action" value="restore_verified"' in maintenance

    assert 'AUTO_RESTORE_KEY = "sg-full-restore-after-verify-v1"' in script
    assert 'actionButton.value = "verify"' in script
    assert "Проверить и восстановить" in script
    assert "event.defaultPrevented" in script
    assert "window.sessionStorage.setItem(AUTO_RESTORE_KEY, file.name)" in script
    assert 'form.dataset.sgFullVerified === "1"' in script
    assert "pendingName !== verifiedName" in script
    assert 'form.dataset.sgConfirmBypass = "1"' in script
    assert "form.requestSubmit(restoreButton)" in script


def test_auto_restore_never_runs_for_unverified_or_unrelated_backup():
    script = SCRIPT.read_text(encoding="utf-8")

    assert "if (pendingName && !hasVerifiedBackup)" in script
    assert "window.sessionStorage.removeItem(AUTO_RESTORE_KEY)" in script
    assert "if (!pendingName || !hasVerifiedBackup || pendingName !== verifiedName) return;" in script
    assert "restoreButton.disabled = false" in script
