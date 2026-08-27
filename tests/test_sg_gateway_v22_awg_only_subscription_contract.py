from pathlib import Path

from jinja2 import Environment

from app.main import _prepare_client_protocols


ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "app" / "main.py"
CLIENTS = ROOT / "app" / "web" / "templates" / "clients.html"
DETAIL = ROOT / "app" / "web" / "templates" / "client_detail.html"
EDIT = ROOT / "app" / "web" / "templates" / "_client_edit_dialogs.html"
HELP = ROOT / "app" / "help" / "content.py"
JS = ROOT / "app" / "web" / "static" / "sg-awg-only-notice-v1.js"


def test_awg_only_protocols_create_without_subscription():
    assert _prepare_client_protocols(
        ["sgclient", "amneziawg", "amneziawg3", "amneziawg31"]
    ) == ["amneziawg", "amneziawg3", "amneziawg31"]


def test_non_awg_protocol_adds_single_subscription_credential():
    assert _prepare_client_protocols(
        ["amneziawg", "mihomo", "sgclient", "mihomo"]
    ) == ["amneziawg", "mihomo", "sgclient"]
    assert _prepare_client_protocols(
        ["xray_reality_tcp"]
    ) == ["xray_reality_tcp", "sgclient"]


def test_all_client_and_device_mutations_use_protocol_normalizer():
    source = MAIN.read_text(encoding="utf-8")
    prepared = (
        'protocols = _prepare_client_protocols('
        'request.form.getlist("protocols"))'
    )
    assert source.count(prepared) == 4
    assert 'protocols = request.form.getlist("protocols")' not in source


def test_forms_do_not_force_sgclient_and_show_awg_only_notice():
    clients = CLIENTS.read_text(encoding="utf-8")
    detail = DETAIL.read_text(encoding="utf-8")
    edit = EDIT.read_text(encoding="utf-8")
    for source in (clients, detail, edit):
        assert 'type="hidden" name="protocols" value="sgclient"' not in source
        Environment().parse(source)

    assert clients.count("SG_AWG_ONLY_NOTICE_V1_CREATE_CLIENT") == 1
    assert detail.count("SG_AWG_ONLY_NOTICE_V1_ADD_DEVICE") == 1
    assert edit.count("SG_AWG_ONLY_NOTICE_V1_EDIT_CLIENT") == 1
    assert edit.count("SG_AWG_ONLY_NOTICE_V1_EDIT_DEVICE") == 1

    notice = (
        "При выборе только AWG-профилей подписка не создаётся. "
        "Используйте QR-коды или файлы конфигурации для каждого соединения."
    )
    assert notice in clients
    assert notice in detail
    assert edit.count(notice) == 2


def test_awg_only_notice_highlights_only_nonempty_all_awg_selection():
    source = JS.read_text(encoding="utf-8")
    assert "selected.length > 0" in source
    assert "selected.every(value => awgOnlyValues.has(value))" in source
    assert "value !== 'sgclient'" in source


def test_help_explains_awg_only_creation_contract():
    source = HELP.read_text(encoding="utf-8")
    assert "SG_GATEWAY_02206_AWG_ONLY_NOTICE_HELP_V2" in source
    assert "клиент и соединения создаются нормально" in source
    assert "SG Client subscription не формируется" in source
