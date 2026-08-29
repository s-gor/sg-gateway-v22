from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "app" / "web" / "templates" / "maintenance.html"
CSS = ROOT / "app" / "web" / "static" / "sg-full-backup-v1.css"


def test_verify_and_restore_share_one_upload_path_without_false_confirmation():
    text = TEMPLATE.read_text(encoding="utf-8")

    assert "url_for('restore_full_backup_route')" in text
    assert 'name="backup_action" value="verify"' in text
    assert "verify_full_backup_route" not in text
    assert 'data-sg-confirm-title="Полное восстановление SG-Gateway"' in text
    assert 'verifyButton.addEventListener("click", () => {' in text
    assert 'form.dataset.sgConfirmBypass = "1"' in text
    assert "delete form.dataset.sgConfirmBypass" in text
    assert "Сначала проверьте файл." in text
    assert "проверен и готов к восстановлению" in text
    assert 'name="backup_action" value="restore_verified"' in text


def test_verify_and_restore_actions_cannot_overflow_restore_area():
    css = CSS.read_text(encoding="utf-8")

    assert ".sg-full-restore-actions{" in css
    assert "flex-wrap:wrap;" in css
    assert "justify-content:flex-start;" in css
    assert ".sg-full-restore-note{" in css
    assert "flex:1 0 100%;" in css
    assert "max-width:none;" in css
    assert ".sg-full-restore-actions .sg-full-restore-button{" in css
    assert "flex:1 1 168px;" in css
    assert "min-width:0;" in css
    assert "max-width:100%;" in css


def test_restore_area_matches_compact_v3_action_zone_contract():
    css = CSS.read_text(encoding="utf-8")

    assert ".sg-full-backup-card::before{display:none!important;content:none!important}" in css
    assert ".sg-full-backup-grid{" in css
    assert "align-items:start;" in css
    assert ".sg-full-restore-box{" in css
    assert "background:transparent!important;" in css
    assert "border:0!important;" in css
    assert "box-shadow:none!important;" in css
    assert ".sg-full-restore-actions .sg-full-verify-button{" in css
    assert "var(--sg-blue) 13%" in css
    assert ".sg-full-restore-actions [data-sg-full-restore-button]{" in css
    assert "var(--sg-yellow) 44%" in css
    assert "#8a5b30" in css
    assert "#6b4427" in css
    assert "border-top:1px solid var(--sg-line-soft)!important;" in css
    assert ".sg-full-restore-actions{align-items:stretch;flex-direction:column}" in css
