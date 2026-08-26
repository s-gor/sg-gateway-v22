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
    assert "SG_NEW_CLIENT_PROTOCOL_PICKER_RESPONSIVE_V1" in css
    assert "grid-template-columns: repeat(5, minmax(0, 1fr)) !important;" in css

    form = text[text.index("url_for('add_client')"):text.index("</form>", text.index("url_for('add_client')"))]
    assert form.count('value="sgclient"') == 1
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
    assert form.index("{% for profile in xray_profiles.profiles %}") < form.index('value="amneziawg"')
