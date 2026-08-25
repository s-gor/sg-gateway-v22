from __future__ import annotations

import json
from pathlib import Path

import pytest
from sg_hostd import awg3_runtime, awg31_runtime, client_runtime

from app import db
from app.clients import awg31_lifecycle as lifecycle
from app.clients import repository

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture()
def isolated_clients(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    database = tmp_path / "sg-gateway.sqlite"
    monkeypatch.setattr(db, "get_database_path", lambda: database)
    counter = iter(range(1, 100))

    def fake_keypair() -> tuple[str, str]:
        value = next(counter)
        return f"awg31-private-{value}", f"awg31-public-{value}"

    def fake_existing_engine(engine: str, access_id: int, label: str):
        payload = {
            "client_name": label,
            "private_key": f"{engine}-private-{access_id}",
            "public_key": f"{engine}-public-{access_id}",
        }
        return payload["public_key"], json.dumps(payload, sort_keys=True)

    monkeypatch.setattr(lifecycle, "_generate_keypair", fake_keypair)
    monkeypatch.setattr(repository, "build_engine_config", fake_existing_engine)
    db.init_db()
    return database


def _credentials(device_id: int) -> dict[str, dict]:
    with db.connect() as connection:
        rows = connection.execute(
            "SELECT engine, config_json FROM device_credentials WHERE device_id = ? ORDER BY engine",
            (device_id,),
        ).fetchall()
    return {str(row["engine"]): json.loads(row["config_json"]) for row in rows}


def _primary_device(client_id: int) -> int:
    with db.connect() as connection:
        row = connection.execute(
            "SELECT id FROM devices WHERE client_id = ? AND is_primary = 1", (client_id,)
        ).fetchone()
    assert row is not None
    return int(row["id"])


def test_three_profiles_have_distinct_ports_interfaces_and_paths() -> None:
    assert client_runtime.AWG_CONFIG == Path("/etc/amnezia/amneziawg/awg0.conf")
    assert awg3_runtime.AWG3_CONFIG == Path("/etc/amnezia/amneziawg/awg3.conf")
    assert lifecycle.SERVER_CONFIG == Path("/etc/amnezia/amneziawg/awg31/awg31.conf")
    assert len({str(client_runtime.AWG_CONFIG), str(awg3_runtime.AWG3_CONFIG), str(lifecycle.SERVER_CONFIG)}) == 3

    assert awg3_runtime.AWG3_ROOT == Path("/opt/sg-gateway/awg3")
    assert lifecycle.RUNTIME_ROOT == Path("/opt/sg-gateway/awg31")
    assert awg3_runtime.AWG3_ROOT != lifecycle.RUNTIME_ROOT
    assert lifecycle.STATE_ROOT == Path("/var/lib/sg-gateway/awg31")
    assert lifecycle.STATE_ROOT not in {
        Path("/var/lib/sg-gateway/awg2"),
        Path("/var/lib/sg-gateway/awg3"),
    }

    assert client_runtime.AWG_SERVICE == "sg-gateway-awg.service"
    assert awg3_runtime.AWG3_SERVICE == "sg-gateway-awg3.service"
    assert awg31_runtime.SERVICE == "sg-gateway-awg31.service"
    assert len({"awg0", "awg3", lifecycle.INTERFACE}) == 3
    assert len({585, awg3_runtime.AWG3_PORT, 587}) == 3


def test_awg31_contract_is_fixed_udp_only() -> None:
    assert lifecycle.PROFILE_ID == "awg31"
    assert lifecycle.ENDPOINT == "awg31.internal:587"
    assert lifecycle.TRANSPORT == "udp"
    assert lifecycle.INTERFACE == "awg31"
    assert lifecycle.NETWORK == "10.131.0.0/24"
    assert lifecycle.DNS == "1.1.1.1"
    assert lifecycle.PEER_CONFIG_DIR == Path("/etc/amnezia/amneziawg/awg31/peers")

    bodies = "\n".join(
        (ROOT / path).read_text(encoding="utf-8")
        for path in (
            "deploy/sg-gateway-awg31-userspace.sh",
            "deploy/sg-gateway-awg31.service",
            "deploy/sg-gateway-awg31ctl",
            "hostd/sg_hostd/awg31_runtime.py",
        )
    ).lower()
    for forbidden in ("listenstream", "sock_stream", "tcp://", "socat tcp", "nc -l"):
        assert forbidden not in bodies


def test_client_create_update_and_awg31_delete_are_isolated(isolated_clients) -> None:
    client_id = repository.create_client("Alpha", "amneziawg,amneziawg3")
    assert client_id is not None
    device_id = _primary_device(client_id)
    before = _credentials(device_id)
    assert set(before) == {"amneziawg", "amneziawg3", "amneziawg31"}
    awg31_before = before["amneziawg31"]
    assert awg31_before["endpoint"] == "awg31.internal:587"
    assert awg31_before["transport"] == "udp"
    assert awg31_before["address"].startswith("10.131.0.")

    assert repository.update_client(client_id, "Alpha Updated", None, "amneziawg,amneziawg3")
    updated = _credentials(device_id)
    assert updated["amneziawg31"]["client_name"] == "Alpha Updated"
    assert updated["amneziawg31"]["private_key"] == awg31_before["private_key"]
    assert updated["amneziawg31"]["public_key"] == awg31_before["public_key"]

    awg2_before = updated["amneziawg"]
    awg3_before = updated["amneziawg3"]
    lifecycle.ensure_peer(device_id, updated["amneziawg31"])
    assert _credentials(device_id)["amneziawg"] == awg2_before
    assert _credentials(device_id)["amneziawg3"] == awg3_before

    assert repository.delete_awg31_peer(device_id) is True
    remaining = _credentials(device_id)
    assert set(remaining) == {"amneziawg", "amneziawg3"}
    assert remaining["amneziawg"] == awg2_before
    assert remaining["amneziawg3"] == awg3_before


def test_client_delete_cascades_its_awg31_peer(isolated_clients) -> None:
    client_id = repository.create_client("Delete Me", "amneziawg,amneziawg3")
    assert client_id is not None
    device_id = _primary_device(client_id)
    assert "amneziawg31" in _credentials(device_id)
    assert repository.delete_client(client_id) is True
    with db.connect() as connection:
        count = connection.execute(
            "SELECT COUNT(*) AS total FROM device_credentials WHERE device_id = ? AND engine = 'amneziawg31'",
            (device_id,),
        ).fetchone()["total"]
    assert int(count) == 0


def test_awg31_renders_separate_server_and_peer_configs(
    isolated_clients, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client_id = repository.create_client("Runtime", "amneziawg,amneziawg3")
    assert client_id is not None
    device_id = _primary_device(client_id)

    config_root = tmp_path / "etc" / "awg31"
    state_root = tmp_path / "state" / "awg31"
    monkeypatch.setattr(awg31_runtime, "SERVER_CONFIG", config_root / "awg31.conf")
    monkeypatch.setattr(awg31_runtime, "PEER_CONFIG_DIR", config_root / "peers")
    monkeypatch.setattr(awg31_runtime, "STATE_ROOT", state_root)
    answers = iter(("server-private", "server-public"))
    monkeypatch.setattr(awg31_runtime, "_run", lambda *args, **kwargs: next(answers))

    result = awg31_runtime.render()
    assert result["profile"] == "awg31"
    assert result["peers"] == 1
    server = (config_root / "awg31.conf").read_text()
    peer = (config_root / "peers" / f"device-{device_id}.conf").read_text()
    assert "ListenPort = 587" in server
    assert "Address = 10.131.0.1/24" in server
    assert "Endpoint = awg31.internal:587" in peer
    assert "DNS = 1.1.1.1" in peer
    assert "TCP" not in server + peer


def test_service_repair_and_control_commands_are_separate() -> None:
    service = (ROOT / "deploy/sg-gateway-awg31.service").read_text()
    repair = (ROOT / "deploy/repair-awg31-runtime.sh").read_text()
    control = (ROOT / "deploy/sg-gateway-awg31ctl").read_text()
    assert "sg-gateway-awg31-userspace.sh" in service
    assert "StateDirectory=sg-gateway/awg31" in service
    assert "amneziawg-tools-3.1.20260812.tar.gz" in repair
    assert "amneziawg-go-linux-amd64-v3.1.20260814" in repair
    assert "/opt/sg-gateway/awg31" in repair
    assert 'install -m 0755 "$PREFIX/deploy/sg-gateway-awg31-userspace.sh" "$PREFIX/deploy/sg-gateway-awg31-userspace.sh"' not in repair
    for action in ("start", "stop", "restart", "status"):
        assert action in control


def test_awg3_remains_30_and_awg31_is_31_with_pinned_hashes() -> None:
    versions = (ROOT / "vendor/cores/VERSIONS.env").read_text()
    sums = (ROOT / "vendor/cores/SHA256SUMS").read_text()
    awg3_repair = (ROOT / "deploy/repair-awg3-runtime.sh").read_text()
    awg31_repair = (ROOT / "deploy/repair-awg31-runtime.sh").read_text()

    assert "AMNEZIAWG3_TOOLS_VERSION=3.0.20260805" in versions
    assert "AMNEZIAWG3_GO_VERSION=3.0.0" in versions
    assert "AMNEZIAWG31_TOOLS_VERSION=3.1.20260812" in versions
    assert "AMNEZIAWG31_GO_VERSION=3.1.20260814" in versions
    assert "090f9383532822a756d078890b447e00af7f46bd30a10f9f47c46d633d807b19  amneziawg-tools-3.0.20260805.tar.gz" in sums
    assert "131110027db6d5dc0e35b19eb5b8a2692676081366c34112088dc68bbb050bcd  amneziawg-go-linux-amd64-v3.0.0" in sums
    assert "f18592c499c893b1b87b15de9e707ce265585cf2536698975b6ede8156d14ada" in sums
    assert "375bc2645df09498aa30215e3b3a09a97626a8e929f409e0edef6564fb8e3110" in sums
    assert "amneziawg-tools-3.0.20260805.tar.gz" in awg3_repair
    assert "amneziawg-go-linux-amd64-v3.0.0" in awg3_repair
    assert "amneziawg-tools-3.1.20260812.tar.gz" in awg31_repair
    assert "amneziawg-go-linux-amd64-v3.1.20260814" in awg31_repair


def test_normal_client_apply_is_extended_with_awg31() -> None:
    assert getattr(client_runtime, "_awg31_apply_installed", False) is True
