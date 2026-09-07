from __future__ import annotations

import app.main as main
from app.clients.repository import create_client, create_device
from tests.ui.html_contract import FormContract, extract_html_contract, require_contract


def _form(action: str, *names: str, data=()):
    return FormContract(
        action=action,
        method="post",
        names=frozenset(names),
        data_hooks=frozenset(data),
    )


def test_02208_clients_and_device_mutation_contracts_are_preserved(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("SG_GATEWAY_ADMIN_PASSWORD", "secret")
    monkeypatch.setenv("SG_GATEWAY_SECRET_KEY", "contract-secret")
    monkeypatch.setenv("SG_GATEWAY_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("SG_GATEWAY_LOG_DIR", str(tmp_path / "logs"))
    monkeypatch.setenv("SG_GATEWAY_PUBLIC_ADDRESS", "203.0.113.10")
    monkeypatch.setenv("SG_GATEWAY_COUNTRY_CODE", "fr")
    app = main.create_app()
    app.jinja_env.globals.update(
        {
            "sg_subscription_universal_url": lambda current_client: f"/contracts/{current_client.id}/universal",
            "sg_subscription_native_url": lambda current_client: f"/contracts/{current_client.id}/native",
            "openwrt_subscription_url": lambda current_client, device: f"/contracts/{current_client.id}/{device.id}/openwrt",
            "keenetic_subscription_url": lambda current_client, device: f"/contracts/{current_client.id}/{device.id}/keenetic",
            "router_subscription_url": lambda current_client, device: f"/contracts/{current_client.id}/{device.id}/router",
            "router_subscription_download_url": lambda current_client, device: f"/contracts/{current_client.id}/{device.id}/router.json",
        }
    )
    http = app.test_client()
    http.post("/login", data={"password": "secret"})
    client_id = create_client("Contract Stage2", "xray")
    assert client_id
    device_id = create_device(client_id, "Tablet", "xray")
    assert device_id

    require_contract(
        extract_html_contract(http.get("/clients").get_data(as_text=True)),
        forms=(
            _form("/clients", "expires_at", "name", "protocols", data=("data-awg-only-note", "data-close-client-form")),
            _form("/clients/apply"),
        ),
        ids=("cv2-dialog", "cv2-search", "cv2-sort", "cv2-table-body", "cv2-apply"),
        data_hooks=("data-open-client-form", "data-client-id", "data-client-name", "data-client-enabled"),
    )

    require_contract(
        extract_html_contract(http.get(f"/clients/{client_id}").get_data(as_text=True)),
        forms=(
            _form(f"/clients/{client_id}/delete", data=("data-sg-confirm", "data-sg-confirm-tone")),
            _form(f"/clients/{client_id}/disable"),
            _form(f"/clients/{client_id}/edit", "expires_at", "name", "protocols", data=("data-close-client-edit",)),
            _form(f"/clients/{client_id}/devices", "expires_at", "name", "protocols", data=("data-close-device-form",)),
            _form(f"/clients/{client_id}/devices/{device_id}/disable"),
            _form(f"/clients/{client_id}/devices/{device_id}/delete", data=("data-sg-confirm", "data-sg-confirm-tone")),
            _form(f"/clients/{client_id}/devices/{device_id}/edit", "expires_at", "name", "protocols", data=("data-close-device-edit",)),
            _form("/clients/apply", "return_client_id"),
        ),
        ids=(f"device-{device_id}", f"dv-edit-device-{device_id}", "dv-edit-client-dialog", "dv46-device-dialog"),
        data_hooks=(
            "data-open-client-edit", "data-open-device-form", "data-open-device-edit", "data-close-device-edit",
            "data-copy-value", "data-sg-subscription-v1", "data-sg-subscription-dual-v1",
            "data-sg-router-keenetic-subscription-v1", "data-sg-router-subscription-v1",
        ),
    )
