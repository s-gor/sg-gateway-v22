from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = (ROOT / "app/web/templates/maintenance.html").read_text(encoding="utf-8")
LEGACY = (ROOT / "app/web/static/sg-maintenance-v2.css").read_text(encoding="utf-8")
PAGE_CSS = ROOT / "app/web/static/sg-ui-maintenance-v22-08.css"


def test_02208_maintenance_owns_page_assets_and_semantic_rails() -> None:
    assert "{% block page_styles %}" in TEMPLATE
    assert "{% block head %}" not in TEMPLATE
    for asset in ("sg-maintenance-v2.css", "sg-maintenance-updates-v31.css", "sg-maintenance-updates-v32.css", "sg-full-backup-v1.css", "sg-ui-maintenance-v22-08.css"):
        assert f"static_asset('{asset}')" in TEMPLATE, asset
    for marker in ('data-sg-ui-page="maintenance"', 'data-sg-section="maintenance-head"', 'data-sg-section="maintenance-tabs"', "sg-ui-page", "sg-ui-page-head", "sg-ui-actions", "sg-ui-section", "sg-ui-section-head"):
        assert marker in TEMPLATE, marker
    assert PAGE_CSS.exists()


def test_02208_maintenance_behavior_contract_stays_intact() -> None:
    for endpoint in ("create_backup_route", "download_diagnostics", "panel_update_start", "xray_update_start", "awg3_runtime_repair_start", "create_full_backup_route", "restore_full_backup_route", "delete_old_backups_route", "restore_backup_route"):
        assert f"url_for('{endpoint}'" in TEMPLATE, endpoint
    for marker in ('name="backup_action" value="verify"', 'name="backup_action" value="restore_verified"', 'data-sg-confirm=', 'data-sg-full-upload', 'data-sg-full-file', 'data-sg-full-verify-button', 'data-sg-full-restore-button'):
        assert marker in TEMPLATE, marker
    assert "active_tab == 'backups'" in TEMPLATE
    assert "active_tab == 'updates'" in TEMPLATE


def test_02208_legacy_maintenance_css_no_longer_owns_page_or_heading_rail() -> None:
    assert not re.search(r"(?m)^\\.mtv2-page\\s*\\{", LEGACY)
    assert not re.search(r"(?m)^\\.mtv2-heading\\s*\\{", LEGACY)
