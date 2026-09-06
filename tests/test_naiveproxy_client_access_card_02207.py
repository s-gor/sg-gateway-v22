from types import SimpleNamespace

from app.clients import access


def test_applied_naiveproxy_credential_gets_direct_link_card(monkeypatch) -> None:
    client = SimpleNamespace(id=7, enabled=True)
    device = SimpleNamespace(id=19, enabled=True, is_primary=False)
    deployment = SimpleNamespace(
        engine="naiveproxy",
        status="applied",
        message="Client provisioned",
        config_json="{}",
    )

    monkeypatch.setattr(access, "list_device_credentials", lambda device_id: [deployment])
    monkeypatch.setattr(
        access,
        "protocol_ready",
        lambda current_client, kind, current_device=None: kind == "naiveproxy",
    )
    monkeypatch.setattr(
        access,
        "build_protocol_export",
        lambda current_client, kind, current_device=None: SimpleNamespace(
            body="naive+https://user:password@example.com:8447#Client%20%C2%B7%20NaiveProxy"
        ),
        raising=False,
    )

    cards = access.build_access_cards(client, device)
    naive = [card for card in cards if card.kind == "naiveproxy"]

    assert len(naive) == 1
    card = naive[0]
    assert card.title == "NaiveProxy"
    assert card.status == "applied"
    assert card.primary_action == "Скачать NaiveProxy-ссылку"
    assert card.export_url == "/clients/7/devices/19/protocols/naiveproxy"
    assert card.qr_url == "/clients/7/devices/19/protocols/naiveproxy/qr"
    assert card.payload.startswith("naive+https://")
    assert ":8447#" in card.payload
