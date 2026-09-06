from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from app import db
from app.clients import awg31_lifecycle, repository

ROOT = Path(__file__).resolve().parents[1]
PROTOCOL_ORDER_MARKERS = (
    "['reality_tcp', 'xhttp_reality']",
    'value="amneziawg"',
    'value="amneziawg3"',
    'value="amneziawg31"',
    'value="mihomo"',
    "['xhttp_tls', 'hysteria2']",
    'value="anytls"',
    'value="tuic"',
)


@pytest.fixture()
def isolated_repository(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    database = tmp_path / "sg-gateway.sqlite"
    monkeypatch.setattr(db, "get_database_path", lambda: database)
    counter = iter(range(1, 100))

    def fake_keypair() -> tuple[str, str]:
        value = next(counter)
        return f"awg31-private-{value}", f"awg31-public-{value}"

    def fake_engine(engine: str, access_id: int, label: str):
        payload = {
            "client_name": label,
            "private_key": f"{engine}-private-{access_id}",
            "public_key": f"{engine}-public-{access_id}",
        }
        return payload["public_key"], json.dumps(payload, sort_keys=True)

    monkeypatch.setattr(awg31_lifecycle, "_generate_keypair", fake_keypair)
    monkeypatch.setattr(repository, "build_engine_config", fake_engine)
    db.init_db()
    return database


def _credential_engines(client_id: int) -> set[str]:
    device = repository.get_primary_device(client_id)
    assert device is not None
    return {item.engine for item in repository.list_device_credentials(device.id)}


def _assert_protocol_order(source: str) -> None:
    positions = [source.index(marker) for marker in PROTOCOL_ORDER_MARKERS]
    assert positions == sorted(positions)


def test_awg31_credential_is_created_only_when_selected(isolated_repository) -> None:
    without_awg31 = repository.create_client("Without AWG31", "amneziawg")
    assert without_awg31 is not None
    assert _credential_engines(without_awg31) == {"amneziawg"}

    with_awg31 = repository.create_client("With AWG31", "amneziawg31")
    assert with_awg31 is not None
    assert _credential_engines(with_awg31) == {"amneziawg31"}


def test_awg31_picker_is_exposed_in_create_and_edit_dialogs() -> None:
    clients = (ROOT / "app/web/templates/clients.html").read_text(encoding="utf-8")
    detail = (ROOT / "app/web/templates/client_detail.html").read_text(encoding="utf-8")
    edits = (ROOT / "app/web/templates/_client_edit_dialogs.html").read_text(encoding="utf-8")
    javascript = (ROOT / "app/web/static/sg-device-collapse-v1.js").read_text(encoding="utf-8")

    assert 'value="amneziawg31"' in clients
    assert 'value="amneziawg31"' in detail
    assert edits.count('value="amneziawg31"') >= 2
    assert "'amneziawg31'" in javascript
    assert "AmneziaWG 3.0" in clients
    assert "AmneziaWG 3.1" in clients


def test_protocol_cards_use_the_same_functional_order_in_all_dialogs() -> None:
    clients = (ROOT / "app/web/templates/clients.html").read_text(encoding="utf-8")
    edits = (ROOT / "app/web/templates/_client_edit_dialogs.html").read_text(encoding="utf-8")

    create_group = re.search(
        r"<!-- SG_PROTOCOL_ORDER_START -->(.*?)<!-- SG_PROTOCOL_ORDER_END -->",
        clients,
        re.S,
    )
    assert create_group is not None
    _assert_protocol_order(create_group.group(1))
    assert "AmneziaWG 2.0" in create_group.group(1)

    edit_groups = re.findall(
        r"<!-- SG_PROTOCOL_ORDER_START -->(.*?)<!-- SG_PROTOCOL_ORDER_END -->",
        edits,
        re.S,
    )
    assert len(edit_groups) == 2
    for group in edit_groups:
        _assert_protocol_order(group)
        assert "AmneziaWG 2.0" in group

    assert "<strong>AmneziaWG 2</strong>" not in clients
    assert "<strong>AmneziaWG 2</strong>" not in edits

    add_device_order = re.search(
        r"SG_ADD_DEVICE_PROTOCOL_ORDER_V2_START(.*?)SG_ADD_DEVICE_PROTOCOL_ORDER_V2_END",
        edits,
        re.S,
    )
    assert add_device_order is not None
    add_device_markers = (
        "'xray_reality_tcp'",
        "'xray_xhttp_reality'",
        "'amneziawg'",
        "'amneziawg3'",
        "'amneziawg31'",
        "'mihomo'",
        "'xray_xhttp_tls'",
        "'xray_hysteria2'",
        "'anytls'",
        "'tuic'",
    )
    positions = [add_device_order.group(1).index(marker) for marker in add_device_markers]
    assert positions == sorted(positions)
    assert "awg2Title.textContent = 'AmneziaWG 2.0'" in add_device_order.group(1)
    assert "const knownValues = new Set(addDeviceProtocolOrder);" in add_device_order.group(1)
    assert "!knownValues.has(value)" in add_device_order.group(1)
    assert "querySelectorAll(':scope > .dv16-protocol')" not in add_device_order.group(1)


def test_all_client_protocol_pickers_use_two_rows_of_five_on_desktop() -> None:
    css = (ROOT / "app/web/static/sg-device-collapse-v4.css").read_text(encoding="utf-8")

    assert "SG_CLIENT_PROTOCOL_DIALOG_LAYOUT_V2" in css
    assert "width: min(1120px, calc(100vw - 32px)) !important;" in css
    assert "max-width: 1120px !important;" in css
    assert "#cv2-dialog .cv12-protocols" in css
    assert ".dv16-dialog .dv16-protocol-list" in css
    assert "grid-template-columns: repeat(5, minmax(0, 1fr)) !important;" in css
    assert "grid-auto-rows: 1fr !important;" in css
    assert "min-height: 72px !important;" in css
    assert "grid-template-columns: 18px minmax(0, 1fr) !important;" in css
    assert "position: static !important;" in css
    assert "1540px" not in css


def test_new_client_picker_uses_one_external_responsive_grid_contract() -> None:
    clients = (ROOT / "app/web/templates/clients.html").read_text(encoding="utf-8")
    css = (ROOT / "app/web/static/sg-device-collapse-v4.css").read_text(encoding="utf-8")

    assert 'id="sg-0217-client-protocol-grid"' not in clients
    assert "SG_CLIENT_PROTOCOL_DIALOG_LAYOUT_V2" in css
    assert "@media (min-width: 981px)" in css
    assert "html body.page-clients #cv2-dialog .cv12-protocols" in css
    assert "html body.page-clients .dv16-dialog .dv16-protocol-list" in css
    assert "grid-template-columns: repeat(5, minmax(0, 1fr)) !important;" in css
    assert "@media (min-width: 721px) and (max-width: 980px)" in css
    assert "grid-template-columns: repeat(2, minmax(0, 1fr)) !important;" in css
    assert "@media (max-width: 720px)" in css
    assert "grid-template-columns: 1fr !important;" in css
    assert "height: 100% !important;" in css
    dialogs = (ROOT / "app/web/templates/_client_edit_dialogs.html").read_text(encoding="utf-8")
    assert "devices-collapse-v4-dialog-layout-v2" not in clients
    assert "devices-collapse-v4-dialog-layout-v2" not in dialogs
    assert "{{ static_asset('sg-device-collapse-v4.css') }}" in clients
    assert "<link rel=\"stylesheet\"" not in dialogs
