from pathlib import Path
import json

ROOT = Path(__file__).resolve().parents[1]


def test_device_technical_profiles_are_always_open() -> None:
    template = (ROOT / "app/web/templates/client_detail.html").read_text(encoding="utf-8")
    assert "Технические ссылки" not in template
    assert '<details class="dv16-technical">' not in template
    assert '<section class="dv16-technical dv16-technical-always-open">' in template
    assert '<div class="dv16-technical-list">' in template


def test_always_open_spacing_and_manifest_contract() -> None:
    css = (ROOT / "app/web/static/sg-clients-simple-hotfix1.css").read_text(encoding="utf-8")
    manifest = json.loads((ROOT / "release-manifest.json").read_text(encoding="utf-8"))
    assert "Clients Always Open Hotfix 3" in css
    assert ".dv16-technical-always-open .dv16-technical-list{margin-top:0}" in css
    assert manifest["clients_ui"]["technical_profiles"] == "collapsed-by-default-independent-device-cards"
    assert manifest["installer_update"]["clients_always_open_hotfix3"] is True
