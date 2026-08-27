from pathlib import Path

from app.mihomo import service as mihomo_service


ROOT = Path(__file__).resolve().parents[1]


def test_client_detail_is_device_first_and_simple() -> None:
    template = (ROOT / "app/web/templates/client_detail.html").read_text(encoding="utf-8")
    assert "Основное устройство" in template
    assert "Скопировать ссылку" in template
    assert "Технические ссылки" not in template
    assert "dv16-technical-always-open" in template
    assert "ДОСТУП ID" not in template
    assert "ПРОФИЛЕЙ" not in template
    assert "Одна подписка для этого устройства" not in template
    assert "dv16-device" in template
    assert "dv16-dialog" in template
    assert 'type="hidden" name="protocols" value="sgclient"' not in template
    assert "SG_AWG_ONLY_NOTICE_V1_ADD_DEVICE" in template


def test_modal_uses_compact_native_checkboxes() -> None:
    css = (ROOT / "app/web/static/sg-clients-simple-hotfix1.css").read_text(encoding="utf-8")
    base = (ROOT / "app/web/templates/base.html").read_text(encoding="utf-8")
    assert "width:min(720px" in css
    assert "max-height:84vh" in css
    assert "appearance:auto!important" in css
    assert "position:sticky" in css
    assert "sg-clients-simple-hotfix1.css" in base


def test_installed_but_stopped_mihomo_runtime_is_error(monkeypatch) -> None:
    monkeypatch.setattr(
        mihomo_service,
        "overview",
        lambda: {
            "installed": True,
            "service_enabled": False,
            "service_active": False,
            "config_exists": False,
            "client_count": 0,
            "version": "Mihomo",
            "protocols": [],
        },
    )
    assert mihomo_service.health_status() == {
        "status": "error",
        "message": "Mihomo установлен, но runtime не запущен",
    }


def test_enabled_but_stopped_mihomo_is_real_error(monkeypatch) -> None:
    monkeypatch.setattr(
        mihomo_service,
        "overview",
        lambda: {
            "installed": True,
            "service_enabled": True,
            "service_active": False,
            "config_exists": True,
            "client_count": 1,
            "version": "Mihomo",
            "protocols": [],
        },
    )
    result = mihomo_service.health_status()
    assert result["status"] == "error"
    assert "включён" in result["message"]


def test_idle_status_is_rendered_as_not_used() -> None:
    for name in ("system.html", "maintenance.html", "recovery.html"):
        template = (ROOT / "app/web/templates" / name).read_text(encoding="utf-8")
        assert "Не используется" in template
