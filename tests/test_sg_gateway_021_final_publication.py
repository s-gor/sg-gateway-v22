from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_working_mihomo_and_singbox_split_is_published():
    service = read("app/mihomo/service.py")
    helper = read("app/mihomo/helper.py")
    exports = read("app/clients/exports.py")
    runtime = read("hostd/sg_hostd/client_runtime.py")
    panel = read("app/web/templates/_mihomo_panel.html")

    assert "SG-Gateway working split runtime" in service
    assert 'settings["anytls_enabled"] = False' in service
    assert 'settings["tuic_enabled"] = False' in service
    assert "def _verify_listeners" not in helper
    assert "mihomo_protocol_active" not in exports
    assert "mihomo_applied_settings" not in exports
    assert "critical_results = [" in runtime
    assert "optional_results.extend(_apply_singbox())" in runtime
    assert "ok = all(result.ok for result in critical_results)" in runtime
    assert "MIHOMO + SING-BOX" in panel
    assert "Mieru обслуживается Mihomo" in panel


def test_global_controls_and_gateway_favicon_are_loaded():
    base = read("app/web/templates/base.html")
    controls = read("app/web/static/sg-controls-final-v1.css")
    favicon = read("app/web/static/favicon.svg")

    assert "sg-controls-final-v1.css" in base
    assert "favicon.svg" in base
    assert "favicon-32.png" in base
    assert "favicon-64.png" in base
    assert "apple-touch-icon.png" in base
    assert "SG-Gateway 021" in controls
    assert "SG" in favicon

    for relative in (
        "app/web/static/favicon-32.png",
        "app/web/static/favicon-64.png",
        "app/web/static/favicon.ico",
        "app/web/static/apple-touch-icon.png",
    ):
        assert (ROOT / relative).stat().st_size > 100


def test_all_page_frames_keep_safe_grid_spacing():
    css = read("app/web/static/sg-page-frame-routing-v1.css")

    assert "SG-Gateway 021 · page frame spacing fix" in css
    assert "gap: 14px !important" in css
    assert "padding: 0 18px 18px !important" in css
    assert "margin: 0 -18px !important" in css


def test_maintenance_has_no_duplicate_summaries_and_checks_are_open():
    template = read("app/web/templates/maintenance.html")
    maintenance_css = read("app/web/static/sg-maintenance-v2.css")
    updates_css = read("app/web/static/sg-maintenance-updates-v31.css")

    assert "mtv2-diagnostics-panel" not in template
    assert "mtv31-update-summary" not in template
    assert "Ещё {{ ns.ok + ns.idle }} обычных проверок" not in template
    assert '<details class="mtv2-ok-checks' not in template
    assert '<div class="mtv2-ok-checks' in template
    assert "Нормальные проверки показаны ниже" in template
    assert template.count("Открыть Status API") == 1
    assert "Для поддержки" in template
    assert "Скачать диагностический отчёт" in template
    assert "SG-Gateway 021 · health checks always open" in maintenance_css
    assert "SG-Gateway 021 · compact support tools" in maintenance_css
    assert "SG-Gateway 021 · clean Maintenance tabs" in updates_css
    assert "SG-Gateway 021 · Maintenance Updates dark-theme" in updates_css


def test_user_and_technical_docs_describe_working_engine_split():
    readme = read("README.md")
    connections = read("docs/CONNECTIONS.md")
    technical = read("docs/TECHNICAL.md")

    assert "Mieru** обслуживается Mihomo" in readme
    assert "AnyTLS** обслуживается отдельным sing-box" in readme
    assert "Mieru обслуживается Mihomo" in connections
    assert "AnyTLS и TUIC v5 обслуживаются отдельным" in connections
    assert "| Mihomo Core | Mieru |" in technical
    assert "| sing-box | AnyTLS и TUIC v5 |" in technical
    assert "не откатывают изменение клиента" in technical
