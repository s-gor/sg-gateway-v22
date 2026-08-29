from __future__ import annotations

import json

import pytest

from app.clients import exports
from app.clients.repository import Client, ClientDeployment, Device


AWG_CONFIGS = {
    "amneziawg": {
        "private_key": "client-private",
        "address": "10.66.0.2/32",
        "server_public_key": "server-public",
        "endpoint": "vpn.example.test:585",
        "jc": 4,
        "jmin": 10,
        "jmax": 50,
        "s1": 64,
        "s2": 96,
        "h1": 1001,
        "h2": 1002,
        "h3": 1003,
        "h4": 1004,
    },
    "amneziawg3": {
        "private_key": "client-private",
        "address": "10.67.0.2/32",
        "server_public_key": "server-public",
        "endpoint": "vpn.example.test:586",
        "jc": 4,
        "jmin": 10,
        "jmax": 50,
        "s1": 64,
        "s2": 96,
        "s3": 48,
        "s4": 12,
        "h1": "1001",
        "h2": "1002",
        "h3": "1003",
        "h4": "1004",
        "header_protection_key": "header-key",
        "content_padding_addition": "10-100",
        "rekey_after_time": "100-120",
        "rekey_timeout": "3-7",
        "reject_after_time": "150-180",
        "keepalive_timeout": "5-15",
        "max_handshake_attempts": "15-20",
    },
    "amneziawg31": {
        "private_key": "client-private",
        "address": "10.131.0.2/32",
        "server_public_key": "server-public",
        "endpoint": "awg31.internal:587",
        "header_protection_key": "header-key",
        "jc": 4,
        "jmin": 10,
        "jmax": 50,
        "s1": 64,
        "s2": 96,
        "s3": 48,
        "s4": 12,
        "h1": "1001",
        "h2": "1002",
        "h3": "1003",
        "h4": "1004",
        "contentpaddingaddition": "10-100",
        "rekeyaftertime": "100-120",
        "rekeytimeout": "3-7",
        "rejectaftertime": "150-180",
        "keepalivetimeout": "5-15",
        "maxhandshakeattempts": "15-20",
        "randomtrailers": "on",
        "disablecookies": "on",
    },
}


def _client() -> Client:
    return Client(
        id=1,
        name="AWG test",
        enabled=True,
        expires_at=None,
        awg_status="applied",
        xray_status="missing",
        awg3_status="applied",
    )


def _device() -> Device:
    return Device(
        id=7,
        client_id=1,
        name="Основной доступ",
        enabled=True,
        expires_at=None,
        is_primary=True,
        created_at="2026-01-01 00:00:00",
    )


def _patch_deployment(monkeypatch: pytest.MonkeyPatch, engine: str, config: dict) -> None:
    deployment = ClientDeployment(
        engine=engine,
        status="applied",
        engine_object_id="object-id",
        config_json=json.dumps(config),
        device_id=7,
    )
    monkeypatch.setattr(
        exports,
        "_deployments",
        lambda client, device=None: {engine: deployment},
    )


@pytest.mark.parametrize("engine", tuple(AWG_CONFIGS))
def test_applied_awg_export_requires_complete_generation_config(
    monkeypatch: pytest.MonkeyPatch,
    engine: str,
) -> None:
    config = dict(AWG_CONFIGS[engine])
    config["private_key"] = ""
    _patch_deployment(monkeypatch, engine, config)

    assert exports.is_export_ready(_client(), engine, _device()) is False


@pytest.mark.parametrize("engine", tuple(AWG_CONFIGS))
def test_complete_applied_awg_export_is_ready(
    monkeypatch: pytest.MonkeyPatch,
    engine: str,
) -> None:
    _patch_deployment(monkeypatch, engine, AWG_CONFIGS[engine])

    assert exports.is_export_ready(_client(), engine, _device()) is True


@pytest.mark.parametrize(
    ("engine", "required_field"),
    (
        ("amneziawg", "h4"),
        ("amneziawg3", "header_protection_key"),
        ("amneziawg31", "disablecookies"),
    ),
)
def test_applied_awg_export_rejects_missing_generation_specific_field(
    monkeypatch: pytest.MonkeyPatch,
    engine: str,
    required_field: str,
) -> None:
    config = dict(AWG_CONFIGS[engine])
    config.pop(required_field)
    _patch_deployment(monkeypatch, engine, config)

    assert exports.is_export_ready(_client(), engine, _device()) is False


def test_applied_awg_export_rejects_malformed_config_json(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    deployment = ClientDeployment(
        engine="amneziawg",
        status="applied",
        engine_object_id="object-id",
        config_json="{not-json",
        device_id=7,
    )
    monkeypatch.setattr(
        exports,
        "_deployments",
        lambda client, device=None: {"amneziawg": deployment},
    )

    assert exports.is_export_ready(
        _client(), "amneziawg", _device()
    ) is False
