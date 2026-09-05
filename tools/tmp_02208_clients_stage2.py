from __future__ import annotations

from pathlib import Path


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if old not in text:
        raise RuntimeError(f"missing expected block: {label}")
    return text.replace(old, new, 1)


def write_tests() -> None:
    Path("tests/test_sg_gateway_v22_clients_geometry_02208.py").write_text(
        r'''from __future__ import annotations

import math

from playwright.sync_api import sync_playwright

import app.main as main
from app.clients.repository import create_client, create_device
from tests.ui.browser_harness import login_panel, rect, serve_app, set_theme

VIEWPORTS = (
    {"width": 1440, "height": 1000},
    {"width": 1024, "height": 900},
    {"width": 390, "height": 844},
)


def _setup_app(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("SG_GATEWAY_ADMIN_PASSWORD", "secret")
    monkeypatch.setenv("SG_GATEWAY_SECRET_KEY", "browser-secret")
    monkeypatch.setenv("SG_GATEWAY_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("SG_GATEWAY_LOG_DIR", str(tmp_path / "logs"))
    monkeypatch.setenv("SG_GATEWAY_PUBLIC_ADDRESS", "203.0.113.10")
    monkeypatch.setenv("SG_GATEWAY_COUNTRY_CODE", "fr")
    app = main.create_app()
    app.jinja_env.globals.update(
        {
            "sg_subscription_universal_url": lambda current_client: f"/contracts/{current_client.id}/universal",
            "sg_subscription_native_url": lambda current_client: f"/contracts/{current_client.id}/native",
            "openwrt_subscription_url": lambda current_client, device: f"/contracts/{current_client.id}/{device.id}/openwrt",
            "keenetic_subscription_url": lambda current_client, device: f"/contracts/{current_client.id}/{device.id}/keenetic",
            "router_subscription_url": lambda current_client, device: f"/contracts/{current_client.id}/{device.id}/router",
            "router_subscription_download_url": lambda current_client, device: f"/contracts/{current_client.id}/{device.id}/router.json",
        }
    )
    client_id = create_client("Browser Client", "xray")
    assert client_id
    device_id = create_device(client_id, "Phone", "xray")
    assert device_id
    return app, client_id


def _assert_close(a: float, b: float, tolerance: float = 1.0) -> None:
    assert math.isclose(a, b, abs_tol=tolerance), (a, b)


def _assert_same_rail(page, selectors):
    geometry = {selector: rect(page, selector) for selector in selectors}
    root = geometry[selectors[0]]
    for selector in selectors[1:]:
        _assert_close(root["x"], geometry[selector]["x"])
        _assert_close(root["width"], geometry[selector]["width"])
    return geometry


def test_02208_clients_and_detail_share_canonical_rail_and_theme_geometry(tmp_path, monkeypatch):
    app, client_id = _setup_app(tmp_path, monkeypatch)
    pages = (
        ("/clients", (
            '[data-sg-ui-page="clients"]',
            '[data-sg-ui-page="clients"] > .sg-ui-page-head',
            '[data-sg-section="clients-filters"]',
            '[data-sg-section="clients-list"]',
        )),
        (f"/clients/{client_id}", (
            '[data-sg-ui-page="client-detail"]',
            '[data-sg-ui-page="client-detail"] > .sg-ui-page-head',
            '[data-sg-section="devices"]',
        )),
    )
    with serve_app(app) as base_url, sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        try:
            for viewport in VIEWPORTS:
                for path, selectors in pages:
                    theme_geometry = {}
                    for theme in ("dark", "light"):
                        page = browser.new_page(viewport=viewport)
                        login_panel(page, base_url, password="secret")
                        set_theme(page, theme)
                        page.goto(f"{base_url}{path}", wait_until="networkidle")
                        assert page.evaluate(
                            "document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1"
                        )
                        theme_geometry[theme] = _assert_same_rail(page, selectors)
                        page.close()
                    for selector in selectors:
                        for key in ("x", "width"):
                            _assert_close(
                                theme_geometry["dark"][selector][key],
                                theme_geometry["light"][selector][key],
                            )
        finally:
            browser.close()
''',
        encoding="utf-8",
    )

    Path("tests/test_sg_gateway_v22_clients_contract_02208.py").write_text(
        r'''from __future__ import annotations

import app.main as main
from app.clients.repository import create_client, create_device
from tests.ui.html_contract import FormContract, extract_html_contract, require_contract


def _form(action: str, *names: str, data=()):
    return FormContract(
        action=action,
        method="post",
        names=frozenset(names),
        data_hooks=frozenset(data),
    )


def test_02208_clients_and_device_mutation_contracts_are_preserved(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("SG_GATEWAY_ADMIN_PASSWORD", "secret")
    monkeypatch.setenv("SG_GATEWAY_SECRET_KEY", "contract-secret")
    monkeypatch.setenv("SG_GATEWAY_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("SG_GATEWAY_LOG_DIR", str(tmp_path / "logs"))
    monkeypatch.setenv("SG_GATEWAY_PUBLIC_ADDRESS", "203.0.113.10")
    monkeypatch.setenv("SG_GATEWAY_COUNTRY_CODE", "fr")
    app = main.create_app()
    app.jinja_env.globals.update(
        {
            "sg_subscription_universal_url": lambda current_client: f"/contracts/{current_client.id}/universal",
            "sg_subscription_native_url": lambda current_client: f"/contracts/{current_client.id}/native",
            "openwrt_subscription_url": lambda current_client, device: f"/contracts/{current_client.id}/{device.id}/openwrt",
            "keenetic_subscription_url": lambda current_client, device: f"/contracts/{current_client.id}/{device.id}/keenetic",
            "router_subscription_url": lambda current_client, device: f"/contracts/{current_client.id}/{device.id}/router",
            "router_subscription_download_url": lambda current_client, device: f"/contracts/{current_client.id}/{device.id}/router.json",
        }
    )
    http = app.test_client()
    http.post("/login", data={"password": "secret"})
    client_id = create_client("Contract Stage2", "xray")
    assert client_id
    device_id = create_device(client_id, "Tablet", "xray")
    assert device_id

    require_contract(
        extract_html_contract(http.get("/clients").get_data(as_text=True)),
        forms=(
            _form("/clients", "expires_at", "name", "protocols", data=("data-awg-only-note", "data-close-client-form")),
            _form("/clients/apply"),
        ),
        ids=("cv2-dialog", "cv2-search", "cv2-sort", "cv2-table-body", "cv2-apply"),
        data_hooks=("data-open-client-form", "data-client-id", "data-client-name", "data-client-enabled"),
    )

    require_contract(
        extract_html_contract(http.get(f"/clients/{client_id}").get_data(as_text=True)),
        forms=(
            _form(f"/clients/{client_id}/delete", data=("data-sg-confirm", "data-sg-confirm-tone")),
            _form(f"/clients/{client_id}/disable"),
            _form(f"/clients/{client_id}/edit", "expires_at", "name", "protocols", data=("data-close-client-edit",)),
            _form(f"/clients/{client_id}/devices", "expires_at", "name", "protocols", data=("data-close-device-form",)),
            _form(f"/clients/{client_id}/devices/{device_id}/disable"),
            _form(f"/clients/{client_id}/devices/{device_id}/delete", data=("data-sg-confirm", "data-sg-confirm-tone")),
            _form(f"/clients/{client_id}/devices/{device_id}/edit", "expires_at", "name", "protocols", data=("data-close-device-edit",)),
            _form("/clients/apply", "return_client_id"),
        ),
        ids=(f"device-{device_id}", f"dv-edit-device-{device_id}", "dv-edit-client-dialog", "dv46-device-dialog"),
        data_hooks=(
            "data-open-client-edit", "data-open-device-form", "data-open-device-edit", "data-close-device-edit",
            "data-copy-value", "data-sg-subscription-v1", "data-sg-subscription-dual-v1",
            "data-sg-router-keenetic-subscription-v1", "data-sg-router-subscription-v1",
        ),
    )
''',
        encoding="utf-8",
    )


def migrate_clients() -> None:
    path = Path("app/web/templates/clients.html")
    text = path.read_text(encoding="utf-8")
    old = """{% block head %}
  {{ super() }}
  <link rel=\"stylesheet\" href=\"{{ url_for('static', filename='sg-clients-visual-v2.css') }}\">
  <link rel=\"stylesheet\" href=\"{{ url_for('static', filename='sg-clients-runtime-v10.css') }}\">
  <link rel=\"stylesheet\" href=\"{{ url_for('static', filename='sg-preview35-clients.css') }}\">
  <link rel=\"stylesheet\" href=\"{{ url_for('static', filename='sg-clients-readable-small-v1.css') }}\">
  <!-- SG_AWG_ONLY_NOTICE_V1_ASSETS -->
  <link rel=\"stylesheet\" href=\"{{ url_for('static', filename='sg-awg-only-notice-v1.css') }}?v={{ app_version }}\">
  <script src=\"{{ url_for('static', filename='sg-awg-only-notice-v1.js') }}?v={{ app_version }}\" defer></script>
{% endblock %}
"""
    new = """{% block head %}
  {{ super() }}
  <script src=\"{{ static_asset('sg-awg-only-notice-v1.js') }}\" defer></script>
{% endblock %}

{% block page_styles %}
  <link rel=\"stylesheet\" href=\"{{ static_asset('sg-clients-visual-v2.css') }}\">
  <link rel=\"stylesheet\" href=\"{{ static_asset('sg-clients-runtime-v10.css') }}\">
  <link rel=\"stylesheet\" href=\"{{ static_asset('sg-preview35-clients.css') }}\">
  <link rel=\"stylesheet\" href=\"{{ static_asset('sg-clients-readable-small-v1.css') }}\">
  <link rel=\"stylesheet\" href=\"{{ static_asset('sg-awg-only-notice-v1.css') }}\">
  <link rel=\"stylesheet\" href=\"{{ static_asset('sg-device-collapse-v4.css') }}\">
  <link rel=\"stylesheet\" href=\"{{ static_asset('sg-device-expanded-cleanup-v1.css') }}\">
  <link rel=\"stylesheet\" href=\"{{ static_asset('sg-ui-clients-v22-08.css') }}\">
{% endblock %}
"""
    text = replace_once(text, old, new, "clients head assets")
    legacy_link = '<link rel="stylesheet" href="{{ url_for(\'static\', filename=\'sg-device-collapse-v4.css\') }}?v={{ app_version }}-devices-collapse-v4-dialog-layout-v2">\n'
    text = replace_once(text, legacy_link, "", "clients content stylesheet")
    text = replace_once(
        text,
        '<section class="cv2-page cv10-page cv35-page cv15-clarity-page">',
        '<section class="cv2-page cv10-page cv35-page cv15-clarity-page sg-ui-page" data-sg-ui-page="clients">',
        "clients page",
    )
    text = replace_once(text, '<header class="cv2-heading cv15-heading">', '<header class="cv2-heading cv15-heading sg-ui-page-head">', "clients heading")
    text = replace_once(text, '<div class="cv2-heading-actions cv10-heading-actions">', '<div class="cv2-heading-actions cv10-heading-actions sg-ui-actions">', "clients actions")
    text = replace_once(
        text,
        '<section id="sg-0217-sg-admin-explainer" class="cv2-filter-panel cv10-filter-panel cv15-filter-panel"',
        '<section id="sg-0217-sg-admin-explainer" class="cv2-filter-panel cv10-filter-panel cv15-filter-panel sg-ui-section sg-ui-card" data-sg-section="clients-admin-explainer"',
        "clients admin explainer",
    )
    text = replace_once(
        text,
        '<section class="cv2-filter-panel cv10-filter-panel cv15-filter-panel" aria-label="Фильтры клиентов">',
        '<section class="cv2-filter-panel cv10-filter-panel cv15-filter-panel sg-ui-section sg-ui-card" data-sg-section="clients-filters" aria-label="Фильтры клиентов">',
        "clients filters",
    )
    text = replace_once(
        text,
        '<section class="cv2-list-panel cv15-list-panel" aria-label="Список клиентов">',
        '<section class="cv2-list-panel cv15-list-panel sg-ui-section sg-ui-card" data-sg-section="clients-list" aria-label="Список клиентов">',
        "clients list",
    )
    path.write_text(text, encoding="utf-8")


def migrate_detail() -> None:
    path = Path("app/web/templates/client_detail.html")
    text = path.read_text(encoding="utf-8")
    old = """{% block head %}
  {{ super() }}
  <link rel=\"stylesheet\" href=\"{{ url_for('static', filename='sg-client-detail-v10.css') }}\">
  <link rel=\"stylesheet\" href=\"{{ url_for('static', filename='sg-devices-v46.css') }}\">
  <link rel=\"stylesheet\" href=\"{{ url_for('static', filename='sg-client-qr-modal-v1.css') }}\">
  <link rel=\"stylesheet\" href=\"{{ url_for('static', filename='sg-subscription-verified-v1.css') }}?v={{ app_version }}\">
  <!-- SG_DEVICE_COLLAPSE_V1_CSS -->
  <link rel=\"stylesheet\" href=\"{{ url_for('static', filename='sg-device-collapse-v1.css') }}?v={{ app_version }}\">
  <!-- /SG_DEVICE_COLLAPSE_V1_CSS -->
  <!-- SG_DEVICE_COLLAPSE_V1_JS -->
  <script src=\"{{ url_for('static', filename='sg-device-collapse-v1.js') }}?v={{ app_version }}\" defer></script>
  <!-- /SG_DEVICE_COLLAPSE_V1_JS -->
  <!-- SG_AWG_ONLY_NOTICE_V1_ASSETS -->
  <link rel=\"stylesheet\" href=\"{{ url_for('static', filename='sg-awg-only-notice-v1.css') }}?v={{ app_version }}\">
  <script src=\"{{ url_for('static', filename='sg-awg-only-notice-v1.js') }}?v={{ app_version }}\" defer></script>
{% endblock %}
"""
    new = """{% block head %}
  {{ super() }}
  <script src=\"{{ static_asset('sg-device-collapse-v1.js') }}\" defer></script>
  <script src=\"{{ static_asset('sg-awg-only-notice-v1.js') }}\" defer></script>
{% endblock %}

{% block page_styles %}
  <link rel=\"stylesheet\" href=\"{{ static_asset('sg-client-detail-v10.css') }}\">
  <link rel=\"stylesheet\" href=\"{{ static_asset('sg-devices-v46.css') }}\">
  <link rel=\"stylesheet\" href=\"{{ static_asset('sg-client-qr-modal-v1.css') }}\">
  <link rel=\"stylesheet\" href=\"{{ static_asset('sg-subscription-verified-v1.css') }}\">
  <link rel=\"stylesheet\" href=\"{{ static_asset('sg-device-collapse-v1.css') }}\">
  <link rel=\"stylesheet\" href=\"{{ static_asset('sg-awg-only-notice-v1.css') }}\">
  <link rel=\"stylesheet\" href=\"{{ static_asset('sg-device-collapse-v4.css') }}\">
  <link rel=\"stylesheet\" href=\"{{ static_asset('sg-device-expanded-cleanup-v1.css') }}\">
  <link rel=\"stylesheet\" href=\"{{ static_asset('sg-ui-clients-v22-08.css') }}\">
{% endblock %}
"""
    text = replace_once(text, old, new, "client detail head assets")
    text = replace_once(text, '<section class="dv16-page">', '<section class="dv16-page sg-ui-page" data-sg-ui-page="client-detail">', "client detail page")
    text = replace_once(text, '<header class="dv16-heading">', '<header class="dv16-heading sg-ui-page-head">', "client detail heading")
    text = replace_once(text, '<div class="dv16-heading-actions">', '<div class="dv16-heading-actions sg-ui-actions">', "client detail actions")
    text = replace_once(
        text,
        '<section class="dv16-devices" aria-label="Устройства клиента">',
        '<section class="dv16-devices sg-ui-section" data-sg-section="devices" aria-label="Устройства клиента">',
        "device section",
    )
    old_article = '<article class="dv16-device {{ \'is-disabled\' if not device.enabled or not client.enabled else \'\' }}" id="device-{{ device.id }}">'
    new_article = '<article class="dv16-device {{ \'is-disabled\' if not device.enabled or not client.enabled else \'\' }} sg-ui-card" data-sg-device-card id="device-{{ device.id }}">'
    text = replace_once(text, old_article, new_article, "device cards")
    path.write_text(text, encoding="utf-8")


def migrate_dialogs() -> None:
    path = Path("app/web/templates/_client_edit_dialogs.html")
    text = path.read_text(encoding="utf-8")
    legacy = '<link rel="stylesheet" href="{{ url_for(\'static\', filename=\'sg-device-collapse-v4.css\') }}?v={{ app_version }}-devices-collapse-v4-dialog-layout-v2">\n'
    if not text.startswith(legacy):
        raise RuntimeError("client edit dialogs no longer starts with legacy stylesheet")
    path.write_text(text[len(legacy):], encoding="utf-8")


def migrate_base() -> None:
    path = Path("app/web/templates/base.html")
    text = path.read_text(encoding="utf-8")
    old = """  {% if active_page|default('') == 'clients' %}
  <!-- SG_DEVICE_COLLAPSE_V4_LAST_CSS -->
  <link rel=\"stylesheet\" href=\"{{ url_for('static', filename='sg-device-collapse-v4.css') }}?v={{ app_version }}-devices-collapse-v4\">
  {% endif %}
  {% if active_page|default('') == 'clients' %}
  <!-- SG_DEVICE_EXPANDED_CLEANUP_V1_LAST_CSS -->
  <link rel=\"stylesheet\" href=\"{{ url_for('static', filename='sg-device-expanded-cleanup-v1.css') }}?v={{ app_version }}-device-expanded-cleanup-v1\">
  {% endif %}
"""
    text = replace_once(text, old, "", "base Clients late CSS")
    path.write_text(text, encoding="utf-8")


def write_css() -> None:
    Path("app/web/static/sg-ui-clients-v22-08.css").write_text(
        '''/* SG-Gateway 22.08 · Clients and Client Detail page ownership. */
[data-sg-ui-page="clients"],
[data-sg-ui-page="client-detail"] {
  width: 100%;
  max-width: none;
  min-width: 0;
  margin: 0;
  padding: 0;
}

[data-sg-ui-page="clients"] > .sg-ui-page-head,
[data-sg-ui-page="client-detail"] > .sg-ui-page-head,
[data-sg-section="clients-admin-explainer"],
[data-sg-section="clients-filters"],
[data-sg-section="clients-list"],
[data-sg-section="devices"] {
  box-sizing: border-box;
  width: 100%;
  max-width: none;
  min-width: 0;
  margin-inline: 0;
}

[data-sg-ui-page="clients"] > .sg-ui-page-head,
[data-sg-ui-page="client-detail"] > .sg-ui-page-head {
  padding-inline: 0;
}

[data-sg-ui-page="clients"] .sg-ui-actions,
[data-sg-ui-page="client-detail"] .sg-ui-actions {
  min-width: 0;
}

[data-sg-section="clients-list"] .cv2-table-scroll,
[data-sg-section="devices"] > [data-sg-device-card] {
  min-width: 0;
  max-width: 100%;
}

@media (max-width: 760px) {
  [data-sg-ui-page="clients"] > .sg-ui-page-head,
  [data-sg-ui-page="client-detail"] > .sg-ui-page-head {
    align-items: stretch;
    flex-direction: column;
  }

  [data-sg-ui-page="clients"] .sg-ui-actions,
  [data-sg-ui-page="client-detail"] .sg-ui-actions {
    width: 100%;
  }
}
''',
        encoding="utf-8",
    )


def main() -> None:
    write_tests()
    migrate_clients()
    migrate_detail()
    migrate_dialogs()
    migrate_base()
    write_css()


if __name__ == "__main__":
    main()
