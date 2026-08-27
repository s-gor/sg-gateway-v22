from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_0217_clients_onboarding_and_protocol_grid():
    text = (ROOT / "app/web/templates/clients.html").read_text(encoding="utf-8")
    css = (ROOT / "app/web/static/sg-device-collapse-v4.css").read_text(encoding="utf-8")

    assert "sg-0217-sg-admin-explainer" in text
    assert "не системный пользователь Linux" in text
    assert "не логин для входа в панель" in text
    assert "sg-admin можно удалить" in text
    assert 'id="sg-0217-client-protocol-grid"' not in text
    assert "SG_CLIENT_PROTOCOL_DIALOG_LAYOUT_V2" in css
    assert "grid-template-columns: repeat(5, minmax(0, 1fr)) !important;" in css
    assert "grid-template-columns: repeat(2, minmax(0, 1fr)) !important;" in css
    assert "grid-template-columns: 1fr !important;" in css

    start = text.index("url_for('add_client')")
    form = text[start:text.index("</form>", start)]
    assert form.count('value="sgclient"') == 0
    assert "SG_AWG_ONLY_NOTICE_V1_CREATE_CLIENT" in form
    main = (ROOT / "app/main.py").read_text(encoding="utf-8")
    assert main.count("_prepare_client_protocols(request.form.getlist") == 4
    assert '<strong>SG Client</strong>' not in form
    for token in (
        'value="amneziawg"',
        'value="amneziawg3"',
        'value="amneziawg31"',
        'value="mihomo"',
        'value="anytls"',
        'value="tuic"',
    ):
        assert token in form
    assert "Требуется HTTPS" in form
    assert form.index("create_xray_protocol_card(xray_profiles.profiles, profile_id)") < form.index('value="amneziawg"')
