from pathlib import Path
import json

from jinja2 import Environment


ROOT = Path(__file__).resolve().parents[1]
CSS_PATH = ROOT / "app/web/static/sg-readable-typography-v3.css"


def test_readable_typography_v3_is_loaded_last_in_panel_shell() -> None:
    base = (ROOT / "app/web/templates/base.html").read_text(encoding="utf-8")
    marker = "sg-readable-typography-v3.css"
    assert marker in base
    assert base.rfind(marker) > base.rfind("sg-clients-clarity-hotfix2.css")
    assert base.rfind(marker) > base.rfind("sg-outbounds-v49.css")
    assert base.rfind(marker) > base.rfind("sg-routing-client096.css")


def test_readable_typography_v3_covers_every_current_page_family() -> None:
    css = CSS_PATH.read_text(encoding="utf-8")
    for marker in (
        ".cv15-clarity-page",
        ".sv1-page",
        ".cnv1-page",
        ".ob49-page",
        ".r096-page",
        ".mtv2-page",
        ".secv2-page",
        ".hlpv1-page",
        ".opjob-page",
        ".login-shell",
        ".recovery-shell",
        ".xps2-salamander",
        ".mhv2-kicker",
        ".gfv1-kicker",
        ".mtv31-update-summary",
    ):
        assert marker in css


def test_readable_typography_v3_changes_only_small_text_scale() -> None:
    css = CSS_PATH.read_text(encoding="utf-8")
    assert "--sgrt-page-kicker: 14px" in css
    assert "--sgrt-small: 13px" in css
    assert "--sgrt-secondary: 14px" in css
    assert "--sgrt-control: 14px" in css
    assert "h1" not in css
    assert "transform: scale(" not in css
    assert "zoom:" not in css


def test_approved_client_detail_typography_is_not_targeted() -> None:
    css = CSS_PATH.read_text(encoding="utf-8")
    assert ".dv16-page" not in css
    assert ".dv16-" not in css
    detail = (ROOT / "app/web/templates/client_detail.html").read_text(encoding="utf-8")
    assert detail.count("+ Добавить устройство") == 1
    assert "dv16-add-bottom" not in detail


def test_standalone_login_and_recovery_load_readable_typography() -> None:
    for name in ("login.html", "recovery.html"):
        source = (ROOT / "app/web/templates" / name).read_text(encoding="utf-8")
        assert "sg-readable-typography-v3.css" in source
        Environment().parse(source)


def test_release_preserves_approved_typography_contract_in_020() -> None:
    version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    manifest = json.loads((ROOT / "release-manifest.json").read_text(encoding="utf-8"))
    assert manifest["version"] == version
    assert manifest["rebuild_policy"]["baseline"] == "0.1.0-021.12"
    update = manifest["installer_update"]
    assert update["global_readable_typography_v018"] is True
    assert update["client_detail_typography_preserved"] is True
