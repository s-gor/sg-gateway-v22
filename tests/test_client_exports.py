import base64

from app.clients.exports import build_mieru_link, build_subscription
from app.clients.repository import create_client, get_client, list_devices
from app.connections.settings import (
    get_connection_settings,
    update_connection_settings,
)
from app.db import connect


def test_client_exports_include_generated_device_values(
    tmp_path,
    monkeypatch,
):
    monkeypatch.chdir(tmp_path)
    client_id = create_client("Irina iPhone", "recommended")
    client = get_client(client_id)
    device = list_devices(client_id)[0]

    with connect() as connection:
        connection.execute(
            "UPDATE device_credentials SET status = 'applied'"
        )

    settings = get_connection_settings("mihomo")
    assert update_connection_settings(
        "mihomo",
        "203.0.113.10",
        settings.port,
        dict(settings.config),
    )

    mieru = build_mieru_link(client, device)
    subscription = build_subscription(client, device)
    decoded = base64.b64decode(subscription.body).decode("utf-8")

    assert mieru.body.startswith("mierus://")
    assert "profile=default" in mieru.body
    assert "Irina%20iPhone" in mieru.body
    # Mieru is an independent optional deployment. A direct link can be
    # rendered, but it must not enter the subscription before deployment.
    assert decoded == ""
