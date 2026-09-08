from __future__ import annotations

import json
from types import SimpleNamespace

from app.clients import access, exports


def _client() -> SimpleNamespace:
    return SimpleNamespace(id=101, name="restored", enabled=True)


def _device() -> SimpleNamespace:
    return SimpleNamespace(id=202, name="phone", enabled=True, is_primary=True)


def _deployment(engine: str, config: dict | None = None) -> SimpleNamespace:
    return SimpleNamespace(
        engine=engine,
        status="applied",
        config_json=json.dumps(config or {}),
    )


def _awg31_complete(server_public_key: str) -> dict:
    return {
        "private_key": "restored-private-key",
        "address": "10.31.0.2/32",
        "server_public_key": server_public_key,
        "endpoint": "old.example:587",
        "header_protection_key": "hp-key",
        "jc": 4,
        "jmin": 10,
        "jmax": 50,
        "s1": 64,
        "s2": 96,
        "s3": 48,
        "s4": 12,
        "h1": "1085466381",
        "h2": "1525636359",
        "h3": "1894947610",
        "h4": "2767261704",
        "contentpaddingaddition": "10-100",
        "rekeyaftertime": "100-120",
        "rekeytimeout": "3-7",
        "rejectaftertime": "150-180",
        "keepalivetimeout": "5-15",
        "maxhandshakeattempts": "15-20",
        "randomtrailers": "on",
        "disablecookies": "on",
    }


def test_awg_access_card_is_dormant_until_protocol_is_export_ready(monkeypatch):
    client = _client()
    device = _device()
    deployment = _deployment("amneziawg", {"private_key": "restored"})

    monkeypatch.setattr(access, "_deployment_map", lambda *_args, **_kwargs: {"amneziawg": deployment})
    monkeypatch.setattr(access, "protocol_ready", lambda *_args, **_kwargs: False)
    monkeypatch.setattr(
        access,
        "build_awg_config",
        lambda *_args, **_kwargs: SimpleNamespace(body="BROKEN-AWG-EXPORT"),
    )

    cards = access.build_access_cards(client, device)

    assert len(cards) == 1
    assert cards[0].kind == "amneziawg"
    assert cards[0].status == "locked"
    assert cards[0].payload == ""


def test_direct_awg_export_is_empty_until_protocol_is_ready(monkeypatch):
    client = _client()
    device = _device()

    monkeypatch.setattr(exports, "protocol_ready", lambda *_args, **_kwargs: False)
    monkeypatch.setattr(
        exports,
        "build_awg3_config",
        lambda *_args, **_kwargs: exports.ClientExport(
            "broken.conf", "text/plain; charset=utf-8", "BROKEN-AWG3-EXPORT"
        ),
    )

    result = exports.build_protocol_export(client, "amneziawg3", device)

    assert result.body == ""


def test_restored_awg31_old_server_key_is_dormant_until_destination_repair(monkeypatch):
    client = _client()
    device = _device()
    deployment = _deployment("amneziawg31", _awg31_complete("SOURCE-SERVER-KEY"))

    monkeypatch.setattr(exports, "_resolve_device", lambda *_args, **_kwargs: device)
    monkeypatch.setattr(exports, "_deployments", lambda *_args, **_kwargs: {"amneziawg31": deployment})
    monkeypatch.setattr(
        exports,
        "get_connection_settings",
        lambda _engine: SimpleNamespace(enabled=True, config={}),
    )
    monkeypatch.setattr(
        exports,
        "get_awg31_settings",
        lambda: SimpleNamespace(enabled=True, server_public_key="DESTINATION-SERVER-KEY"),
    )

    assert exports.is_export_ready(client, "amneziawg31", device) is False


def test_repaired_awg31_same_client_key_becomes_export_ready(monkeypatch):
    client = _client()
    device = _device()
    config = _awg31_complete("DESTINATION-SERVER-KEY")
    deployment = _deployment("amneziawg31", config)

    monkeypatch.setattr(exports, "_resolve_device", lambda *_args, **_kwargs: device)
    monkeypatch.setattr(exports, "_deployments", lambda *_args, **_kwargs: {"amneziawg31": deployment})
    monkeypatch.setattr(
        exports,
        "get_connection_settings",
        lambda _engine: SimpleNamespace(enabled=True, config={}),
    )
    monkeypatch.setattr(
        exports,
        "get_awg31_settings",
        lambda: SimpleNamespace(enabled=True, server_public_key="DESTINATION-SERVER-KEY"),
    )

    assert exports.is_export_ready(client, "amneziawg31", device) is True
    assert json.loads(deployment.config_json)["private_key"] == "restored-private-key"
