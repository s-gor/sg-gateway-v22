from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def source(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_0219_version_and_manifest_are_synchronized() -> None:
    version = source("VERSION").strip()
    manifest = json.loads(source("release-manifest.json"))
    assert version == "0.1.0-022.04"
    assert manifest["version"] == version
    assert manifest["rebuild_policy"]["baseline"] == "0.1.0-021.12"
    assert manifest["mieru_export"]["ordinary_uri"] is True
    assert manifest["mieru_export"]["separate_json"] is True
    assert manifest["mieru_export"]["separate_json_qr"] is True
    assert manifest["mieru_export"]["shared_subscription_inclusion"] is False


def test_mieru_link_json_and_two_qr_exports_are_present() -> None:
    exports = source("app/clients/exports.py")
    access = source("app/clients/access.py")
    template = source("app/web/templates/client_detail.html")
    assert "def build_mieru_link(" in exports
    assert "def build_mieru_json(" in exports
    assert '"mieru-json": "mihomo"' in exports
    assert '"mieru-json": build_mieru_json' in exports
    assert "payload=build_mieru_link" in access
    assert "secondary_payload=(" in access
    assert "secondary_qr_url=(" in access
    assert 'tertiary_label="Mihomo YAML"' in access
    assert ">QR JSON<" in template
    assert "card.qr_url" in template
    assert "card.secondary_qr_url" in template


def test_shared_subscription_excludes_mieru_and_uses_real_newlines() -> None:
    exports = source("app/clients/exports.py")
    start = exports.index("def build_subscription(")
    block = exports[start:]
    assert r'decoded = "\n".join' in block
    assert r'decoded = "\\n".join' not in block
    assert "build_mieru_link" not in block
    assert "mierus://" not in block


def test_mobile_sidebar_is_published_linked_and_desktop_safe() -> None:
    base = source("app/web/templates/base.html")
    mobile = source("app/web/static/sg-mobile-sidebar-v1.css")
    manifest = json.loads(source("release-manifest.json"))
    assert "sg-mobile-sidebar-v1.css" in base
    assert "@media (max-width: 760px)" in mobile
    assert "Mobile navigation only. Desktop layout is untouched." in mobile
    assert "sidebar-collapsed .sg-nav" in mobile
    assert 'content: "Развернуть меню"' in mobile
    assert manifest["clients_ui"]["mobile_sidebar"] == "accepted-responsive-v1"
    assert manifest["clients_ui"]["desktop_layout_untouched"] is True


def test_client_and_device_editing_preserves_unchanged_credentials() -> None:
    repository = source("app/clients/repository.py")
    main = source("app/main.py")
    detail = source("app/web/templates/client_detail.html")
    dialogs = source("app/web/templates/_client_edit_dialogs.html")
    assert "def update_client(" in repository
    assert "def update_device(" in repository
    assert "without rotating unchanged secrets" in repository
    assert '@app.post("/clients/<int:client_id>/edit")' in main
    assert '@app.post("/clients/<int:client_id>/devices/<int:device_id>/edit")' in main
    assert "_rollback_client_change(snapshot, exc)" in main
    assert '_client_edit_dialogs.html' in detail
    assert "Неизменённые UUID, пароли, токены и ссылки не перевыпускаются" in dialogs


def test_public_subscription_url_and_extension_free_title_are_present() -> None:
    exports = source("app/clients/exports.py")
    access = source("app/clients/access.py")
    main = source("app/main.py")
    assert "def build_subscription_url(" in exports
    assert "subscription_url = build_subscription_url(client, device)" in access
    assert '@app.get("/sub/<token>")' in main
    marker = main.index("SG_GATEWAY_SUBSCRIPTION_PATCH_V1")
    end = main.index("return response", marker)
    metadata = main[marker:end]
    assert 'response.headers["Profile-Title"]' in metadata
    assert 'response.headers["Content-Disposition"]' in metadata
    assert ".txt" not in metadata
