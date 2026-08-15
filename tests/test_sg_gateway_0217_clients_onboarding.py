from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def test_0217_clients_onboarding_and_protocol_grid():
    text = (ROOT / "app/web/templates/clients.html").read_text(encoding="utf-8")
    assert "sg-0217-sg-admin-explainer" in text
    assert "не системный пользователь Linux" in text
    assert "не логин для входа в панель" in text
    assert "sg-admin можно удалить" in text
    assert "grid-template-columns: repeat(4, minmax(0, 1fr))" in text
    form = text[text.index("url_for('add_client')"):text.index("</form>", text.index("url_for('add_client')"))]
    assert form.count('value="sgclient"') == 1
    assert '<strong>SG Client</strong>' not in form
    for token in ('value="amneziawg"', 'value="mihomo"', 'value="anytls"', 'value="tuic"'):
        assert token in form
    assert "Требуется HTTPS" in form
    assert form.index("{% for profile in xray_profiles.profiles %}") < form.index('value="amneziawg"')
