from __future__ import annotations

from pathlib import Path

from app.security.sg_infosec_presentation_runtime import (
    register_sg_infosec_presentation,
)


class OverviewSource:
    def __init__(self, payload):
        self.payload = payload
        self.calls = 0

    def overview(self):
        self.calls += 1
        return self.payload


class AppStub:
    def __init__(self, management, engine):
        self.extensions = {
            "sg_infosec_management": {"client": management},
            "sg_infosec_guard": {"engine": engine},
        }


def test_runtime_wraps_management_and_guard_overviews_once():
    management = OverviewSource(
        {
            "available": True,
            "status": "Работает",
            "active_decisions": [],
            "history": [],
            "allowlist": [],
            "audit": [],
        }
    )
    guard = OverviewSource({"alerts": [], "settings": {}, "counters": {}})
    app = AppStub(management, guard)

    register_sg_infosec_presentation(app)
    register_sg_infosec_presentation(app)

    assert management.overview()["available"] is True
    assert guard.overview()["alerts"] == []
    assert management.calls == 1
    assert guard.calls == 1
    assert app.extensions["sg_infosec_presentation"] is True


def test_management_template_uses_readable_cards_and_disclosures():
    template = Path("app/web/templates/_sg_infosec_management_base.html").read_text(
        encoding="utf-8"
    )
    for contract in (
        "infosec-decision-list",
        "infosec-decision-card",
        "item.ip_intel.summary",
        "item.scope_label",
        "item.reason_label",
        "item.scope_effect",
        "item.expires_at_label",
        "Технические данные",
        "infosec-disclosure",
        "Добавить исключение",
        "Заблокировать IP",
    ):
        assert contract in template
    assert "<th>ОБЛАСТЬ</th>" not in template
    assert "{{ item.reason_code }}" not in template
    assert "{{ item.state }}" not in template
    assert "{{ item.action }}" not in template


def test_guard_template_uses_human_labels_and_network_identity():
    template = Path("app/web/templates/_sg_infosec_guard.html").read_text(
        encoding="utf-8"
    )
    for contract in (
        "infosec-alert-list",
        "item.action_label",
        "item.rule_labels",
        "item.scope_label",
        "item.ip_intel.summary",
        "item.occurred_at_label",
        "Технические данные",
    ):
        assert contract in template
    assert "item.rule_ids | join" not in template


def test_readable_layout_removes_mandatory_horizontal_tables():
    css = Path("app/web/static/sg-infosec-readable-v2.css").read_text(
        encoding="utf-8"
    )
    compact = css.replace(" ", "")
    for contract in (
        ".infosec-decision-list",
        ".infosec-decision-card",
        ".infosec-alert-list",
        ".infosec-history-stack",
        ".infosec-disclosure",
    ):
        assert contract in css
    assert "overflow-wrap:anywhere" in compact
    assert "overflow-x:auto" not in compact


def test_built_in_manual_explains_ip_ownership_privacy_and_effect():
    template = Path("app/web/templates/sg_infosec_help_v2.html").read_text(
        encoding="utf-8"
    )
    runtime = Path(
        "app/security/sg_infosec_presentation_runtime.py"
    ).read_text(encoding="utf-8")
    for contract in (
        "Кому принадлежит адрес",
        "Это сведения о сети, а не установление личности",
        "RIPEstat",
        "не создают блокировку",
        "SG_INFOSEC_IP_INTEL_ENABLED=0",
    ):
        assert contract in template
    assert "sg_infosec_help_v2.html" in runtime
    assert "security_infosec_help" in runtime


def test_ip_intelligence_cache_is_persistent_in_service_and_update_contracts():
    unit = Path("deploy/systemd/sg-gateway.service").read_text(encoding="utf-8")
    migration = Path("app/security/sg_infosec_unit_migration.py").read_text(
        encoding="utf-8"
    )
    updater = Path("deploy/update-infosec-complete-from-github.sh").read_text(
        encoding="utf-8"
    )
    expected = (
        "SG_INFOSEC_IP_INTEL_CACHE="
        "/var/lib/sg-gateway/infosec/ip-intelligence.json"
    )
    assert expected in unit
    assert expected in migration
    assert expected in updater
