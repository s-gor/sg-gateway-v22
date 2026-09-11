from pathlib import Path


def _read(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


def test_all_client_device_protocol_forms_have_native_naiveproxy_card():
    clients = _read("app/web/templates/clients.html")
    detail = _read("app/web/templates/client_detail.html")
    edits = _read("app/web/templates/_client_edit_dialogs.html")

    assert clients.count('value="naiveproxy"') == 1
    assert detail.count('value="naiveproxy"') == 1
    assert edits.count('value="naiveproxy"') == 2
    assert 'class="cv10-protocol' in clients
    assert 'class="dv16-protocol' in detail
    assert edits.count('class="dv16-protocol') >= 3


def test_obsolete_awg_only_subscription_notice_is_gone_from_client_forms():
    combined = "\n".join([
        _read("app/web/templates/clients.html"),
        _read("app/web/templates/client_detail.html"),
        _read("app/web/templates/_client_edit_dialogs.html"),
    ])
    assert "При выборе только AWG-профилей подписка не создаётся" not in combined
    assert "sg-awg-only-note" not in combined
    assert "sg-awg-only-notice-v1.js" not in combined
    assert "sg-awg-only-notice-v1.css" not in combined
