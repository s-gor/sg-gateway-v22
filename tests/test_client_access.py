from app.clients.access import build_access_cards
from app.clients.repository import create_client, get_client


def test_build_access_cards_for_recommended_client(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    client_id = create_client("Irina iPhone", "recommended")
    client = get_client(client_id)

    cards = build_access_cards(client)
    titles = [card.title for card in cards]

    assert "VLESS XHTTP Reality" in titles
    assert "Mieru" not in titles
    assert "Подписка устройства" in titles
    assert "AmneziaWG" not in titles
    assert all(
        f"/clients/{client_id}/devices/" in card.export_url
        for card in cards if card.export_url
    )
