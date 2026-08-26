from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from app import db
from app.clients import awg31_lifecycle, repository

SERVER_PUBLIC_KEY = "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="

VALID_PARAMETERS = {
    "I1": "<b 0x160301>",
    "I2": "<r 16><t>",
    "I3": "<rd 12>",
    "I4": "<rc 24>",
    "I5": "<b 0x01020304><r 8>",
    "Jc": 7,
    "Jmin": 40,
    "Jmax": 120,
    "S1": 128,
    "S2": 256,
    "S3": 384,
    "S4": 512,
    "H1": "1001",
    "H2": "2000-2002",
    "H3": "3003",
    "H4": "4000-4010",
}


@pytest.fixture()
def isolated_stage2(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
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

    monkeypatch.setattr(awg31_lifecycle, "_generate_keypair", fake_keypair)
    monkeypatch.setattr(repository, "build_engine_config", fake_existing_engine)
    db.init_db()
    return database


def _authenticate(client) -> None:
    with client.session_transaction() as session:
        session["authenticated"] = True


def _primary_device(client_id: int) -> int:
    with db.connect() as connection:
        row = connection.execute(
            "SELECT id FROM devices WHERE client_id = ? AND is_primary = 1",
            (client_id,),
        ).fetchone()
    assert row is not None
    return int(row["id"])


def _credential(device_id: int, engine: str) -> dict:
    with db.connect() as connection:
        row = connection.execute(
            "SELECT config_json FROM device_credentials WHERE device_id = ? AND engine = ?",
            (device_id, engine),
        ).fetchone()
    assert row is not None
    return json.loads(row["config_json"])


def test_all_awg31_fields_round_trip_through_model_and_api(isolated_stage2) -> None:
    from app.connections.awg31 import get_settings, save_settings
    from app.main import create_app

    saved = save_settings(VALID_PARAMETERS)
    assert saved.parameters == VALID_PARAMETERS
    assert get_settings().parameters == VALID_PARAMETERS

    app = create_app()
    client = app.test_client()
    _authenticate(client)

    response = client.get("/api/connections/awg31")
    assert response.status_code == 200
    assert response.get_json()["parameters"] == VALID_PARAMETERS

    updated = dict(VALID_PARAMETERS)
    updated["I3"] = "<b 0xfeed><rd 4>"
    updated["Jc"] = 9
    response = client.put("/api/connections/awg31", json={"parameters": updated})
    assert response.status_code == 200
    assert response.get_json()["parameters"] == updated
    assert get_settings().parameters == updated


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("Jc", -1),
        ("Jmax", 65536),
        ("S1", "not-a-number"),
        ("H1", "4-3"),
        ("H2", "4294967296"),
        ("H3", "1-two"),
        ("I1", "alpha-tag"),
        ("I1", "beta tag"),
        ("I1", "03:payload"),
        ("I1", "<b 0x123>"),
        ("I2", "<unknown 1>"),
        ("I3", "<rd 12"),
        ("I4", "<rc -1>"),
        ("I5", "<r 2000>"),
        ("I5", "<b 0x00>" * 1400),
    ],
)
def test_awg31_validation_rejects_invalid_values(field: str, value: object) -> None:
    from app.connections.awg31 import Awg31ValidationError, validate_parameters

    payload = dict(VALID_PARAMETERS)
    payload[field] = value
    with pytest.raises(Awg31ValidationError):
        validate_parameters(payload)


def test_awg31_validation_rejects_jmin_greater_than_jmax() -> None:
    from app.connections.awg31 import Awg31ValidationError, validate_parameters

    payload = dict(VALID_PARAMETERS, Jmin=121, Jmax=120)
    with pytest.raises(Awg31ValidationError):
        validate_parameters(payload)


def test_ui_edit_updates_only_awg31_settings(isolated_stage2) -> None:
    from app.connections.awg31 import get_settings
    from app.main import create_app

    with db.connect() as connection:
        before = {
            row["engine"]: (row["host"], row["port"], row["config_json"])
            for row in connection.execute(
                "SELECT engine, host, port, config_json FROM connection_settings "
                "WHERE engine IN ('amneziawg', 'amneziawg3')"
            ).fetchall()
        }

    app = create_app()
    client = app.test_client()
    _authenticate(client)
    response = client.post("/connections/amneziawg31", data=VALID_PARAMETERS)
    assert response.status_code == 302
    assert get_settings().parameters == VALID_PARAMETERS

    with db.connect() as connection:
        after = {
            row["engine"]: (row["host"], row["port"], row["config_json"])
            for row in connection.execute(
                "SELECT engine, host, port, config_json FROM connection_settings "
                "WHERE engine IN ('amneziawg', 'amneziawg3')"
            ).fetchall()
        }
    assert after == before


def test_api_rejects_invalid_payload_and_does_not_change_awg2_or_awg3(
    isolated_stage2,
) -> None:
    from app.main import create_app

    with db.connect() as connection:
        before = {
            row["engine"]: (row["host"], row["port"], row["config_json"])
            for row in connection.execute(
                "SELECT engine, host, port, config_json FROM connection_settings "
                "WHERE engine IN ('amneziawg', 'amneziawg3')"
            ).fetchall()
        }

    app = create_app()
    client = app.test_client()
    _authenticate(client)
    response = client.put(
        "/api/connections/awg31",
        json={"parameters": dict(VALID_PARAMETERS, Jmin=500, Jmax=100)},
    )
    assert response.status_code == 400

    with db.connect() as connection:
        after = {
            row["engine"]: (row["host"], row["port"], row["config_json"])
            for row in connection.execute(
                "SELECT engine, host, port, config_json FROM connection_settings "
                "WHERE engine IN ('amneziawg', 'amneziawg3')"
            ).fetchall()
        }
    assert after == before


def test_server_and_peer_configs_contain_every_awg31_parameter(
    isolated_stage2,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from sg_hostd import awg31_runtime

    from app.connections.awg31 import save_settings

    save_settings(VALID_PARAMETERS)
    client_id = repository.create_client("Stage 2", "amneziawg,amneziawg3,amneziawg31")
    assert client_id is not None
    device_id = _primary_device(client_id)

    root = tmp_path / "awg31"
    monkeypatch.setattr(awg31_runtime, "SERVER_CONFIG", root / "awg31.conf")
    monkeypatch.setattr(awg31_runtime, "PEER_CONFIG_DIR", root / "peers")
    monkeypatch.setattr(awg31_runtime, "STATE_ROOT", root / "state")
    monkeypatch.setattr(
        awg31_runtime,
        "_server_keys",
        lambda: ("server-private", "server-public"),
    )

    result = awg31_runtime.render()
    assert result["profile"] == "awg31"
    server = (root / "awg31.conf").read_text(encoding="utf-8")
    peer = (root / "peers" / f"device-{device_id}.conf").read_text(encoding="utf-8")
    for name, value in VALID_PARAMETERS.items():
        assert f"{name} = {value}" in server
        assert f"{name} = {value}" in peer


def test_awg31_config_and_uri_exports_are_profile_specific(isolated_stage2) -> None:
    from app.clients.exports import build_awg31_config, build_awg31_uri
    from app.connections.awg31 import save_settings, set_server_public_key

    save_settings(VALID_PARAMETERS)
    set_server_public_key(SERVER_PUBLIC_KEY)
    client_id = repository.create_client("Export 31", "amneziawg,amneziawg3,amneziawg31")
    assert client_id is not None
    device_id = _primary_device(client_id)
    with db.connect() as connection:
        connection.execute(
            "UPDATE device_credentials SET status = 'applied' "
            "WHERE device_id = ? AND engine = 'amneziawg31'",
            (device_id,),
        )
    client = repository.get_client(client_id)
    device = repository.get_device(client_id, device_id)
    assert client is not None and device is not None

    config = build_awg31_config(client, device)
    uri = build_awg31_uri(client, device)
    assert config.filename.endswith("-amneziawg31.conf")
    assert "Endpoint = awg31.internal:587" in config.body
    assert "DNS = 1.1.1.1" in config.body
    assert "# Transport: UDP" in config.body
    for name, value in VALID_PARAMETERS.items():
        assert f"{name} = {value}" in config.body

    assert uri.filename.endswith("-amneziawg31-uri.txt")
    from app.connections.awg31_uri import decode_awg31_uri

    decoded = decode_awg31_uri(uri.body)
    assert decoded["profile"] == "awg31"
    assert decoded["endpoint"] == "awg31.internal:587"
    assert decoded["transport"] == "udp"
    assert decoded["dns"] == "1.1.1.1"
    assert decoded["parameters"] == VALID_PARAMETERS



def _install_isolated_awg31_runtime(tmp_path: Path) -> Path:
    prefix = tmp_path / "runtime-prefix"
    vendor = prefix / "vendor" / "cores"
    deploy = prefix / "deploy"
    vendor.mkdir(parents=True)
    deploy.mkdir(parents=True)
    for filename in (
        "amneziawg-tools-3.1.20260812.tar.gz",
        "amneziawg-go-linux-amd64-v3.1.20260814",
    ):
        shutil.copy2(Path("vendor/cores") / filename, vendor / filename)
    shutil.copy2(
        Path("deploy/sg-gateway-awg31.service"),
        deploy / "sg-gateway-awg31.service",
    )
    runtime = prefix / "awg31"
    env = os.environ.copy()
    env.update(
        {
            "SG_GATEWAY_PREFIX": str(prefix),
            "SG_GATEWAY_AWG31_RUNTIME": str(runtime),
            "SG_GATEWAY_AWG31_CONFIG_ROOT": str(prefix / "config"),
            "SG_GATEWAY_AWG31_STATE_ROOT": str(prefix / "state"),
            "SG_GATEWAY_SYSTEMD_DIR": str(prefix / "systemd"),
            "SG_GATEWAY_SKIP_SYSTEMCTL": "1",
        }
    )
    subprocess.run(
        ["bash", "deploy/repair-awg31-runtime.sh"],
        env=env,
        text=True,
        capture_output=True,
        check=True,
    )
    return runtime


def _real_keypair(awg: Path) -> tuple[str, str]:
    private = subprocess.run(
        [str(awg), "genkey"], text=True, capture_output=True, check=True
    ).stdout.strip()
    public = subprocess.run(
        [str(awg), "pubkey"],
        input=private + "\n",
        text=True,
        capture_output=True,
        check=True,
    ).stdout.strip()
    return private, public


def _assert_real_awg_parser_accepts(awg: Path, awg_quick: Path, config: Path) -> None:
    stripped = config.with_suffix(config.suffix + ".stripped")
    strip = subprocess.run(
        [str(awg_quick), "strip", str(config)],
        text=True,
        capture_output=True,
        check=False,
        timeout=15,
    )
    assert strip.returncode == 0, strip.stdout + strip.stderr
    stripped.write_text(strip.stdout, encoding="utf-8")

    shim = config.parent / "libawg31-resolver.so"
    if not shim.exists():
        source = config.parent / "awg31-resolver.c"
        source.write_text(
            "#define _GNU_SOURCE\n"
            "#include <dlfcn.h>\n"
            "#include <netdb.h>\n"
            "#include <string.h>\n\n"
            "typedef int (*getaddrinfo_fn)(const char *, const char *, "
            "const struct addrinfo *, struct addrinfo **);\n\n"
            "int getaddrinfo(const char *node, const char *service, "
            "const struct addrinfo *hints, struct addrinfo **result) {\n"
            "    static getaddrinfo_fn real_getaddrinfo = NULL;\n"
            "    if (real_getaddrinfo == NULL)\n"
            "        real_getaddrinfo = (getaddrinfo_fn)dlsym(RTLD_NEXT, "
            "\"getaddrinfo\");\n"
            "    if (node != NULL && strcmp(node, \"awg31.internal\") == 0)\n"
            "        node = \"127.0.0.1\";\n"
            "    return real_getaddrinfo(node, service, hints, result);\n"
            "}\n",
            encoding="utf-8",
        )
        subprocess.run(
            ["cc", "-shared", "-fPIC", "-o", str(shim), str(source), "-ldl"],
            text=True,
            capture_output=True,
            check=True,
            timeout=30,
        )
    env = os.environ.copy()
    env["LD_PRELOAD"] = str(shim)
    parsed = subprocess.run(
        [str(awg), "setconf", "awg31-parser-probe", str(stripped)],
        text=True,
        capture_output=True,
        check=False,
        timeout=15,
        env=env,
    )
    assert parsed.returncode != 0
    assert "Configuration parsing error" not in parsed.stderr
    assert "Unable to modify interface" in parsed.stderr

def test_empty_i_fields_are_omitted_and_filled_configs_pass_real_awg31_parser(
    isolated_stage2,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from sg_hostd import awg31_runtime

    from app.clients.exports import build_awg31_config
    from app.connections.awg31 import DEFAULT_PARAMETERS, save_settings

    client_id = repository.create_client("Parser 31", "amneziawg,amneziawg3,amneziawg31")
    assert client_id is not None
    device_id = _primary_device(client_id)
    root = tmp_path / "rendered"
    monkeypatch.setattr(awg31_runtime, "SERVER_CONFIG", root / "awg31.conf")
    monkeypatch.setattr(awg31_runtime, "PEER_CONFIG_DIR", root / "peers")
    monkeypatch.setattr(awg31_runtime, "STATE_ROOT", root / "state")

    runtime = _install_isolated_awg31_runtime(tmp_path)
    awg = runtime / "bin" / "awg"
    awg_quick = runtime / "bin" / "awg-quick"
    peer_private, peer_public = _real_keypair(awg)
    server_private, server_public = _real_keypair(awg)
    with db.connect() as connection:
        row = connection.execute(
            "SELECT id, config_json FROM device_credentials "
            "WHERE device_id = ? AND engine = 'amneziawg31'",
            (device_id,),
        ).fetchone()
        assert row is not None
        payload = json.loads(row["config_json"])
        payload["private_key"] = peer_private
        payload["public_key"] = peer_public
        connection.execute(
            "UPDATE device_credentials SET config_json = ? WHERE id = ?",
            (json.dumps(payload, sort_keys=True), int(row["id"])),
        )
    monkeypatch.setattr(
        awg31_runtime, "_server_keys", lambda: (server_private, server_public)
    )

    save_settings(DEFAULT_PARAMETERS)
    awg31_runtime.render()
    client = repository.get_client(client_id)
    device = repository.get_device(client_id, device_id)
    assert client is not None and device is not None
    default_export = build_awg31_config(client, device)
    default_peer = root / "peers" / f"device-{device_id}.conf"
    for body in (
        (root / "awg31.conf").read_text(encoding="utf-8"),
        default_peer.read_text(encoding="utf-8"),
        default_export.body,
    ):
        for name in ("I1", "I2", "I3", "I4", "I5"):
            assert f"{name} =" not in body

    save_settings(VALID_PARAMETERS)
    awg31_runtime.render()
    export = build_awg31_config(client, device)
    export_path = root / "export.conf"
    export_path.write_text(export.body, encoding="utf-8")
    for config_path in (root / "awg31.conf", default_peer, export_path):
        text = config_path.read_text(encoding="utf-8")
        for name in ("I1", "I2", "I3", "I4", "I5"):
            assert f"{name} = {VALID_PARAMETERS[name]}" in text
        _assert_real_awg_parser_accepts(awg, awg_quick, config_path)


def test_awg31_uri_consumer_round_trips_complete_configuration(isolated_stage2) -> None:
    from app.clients.awg31_stage2 import build_awg31_config, build_awg31_uri
    from app.connections.awg31 import save_settings, set_server_public_key
    from app.connections.awg31_uri import decode_awg31_uri

    save_settings(VALID_PARAMETERS)
    set_server_public_key(SERVER_PUBLIC_KEY)
    client_id = repository.create_client("URI 31", "amneziawg,amneziawg3,amneziawg31")
    assert client_id is not None
    device_id = _primary_device(client_id)
    client = repository.get_client(client_id)
    device = repository.get_device(client_id, device_id)
    assert client is not None and device is not None

    config = build_awg31_config(client, device)
    uri = build_awg31_uri(client, device)
    decoded = decode_awg31_uri(uri.body)

    assert decoded["profile"] == "awg31"
    assert decoded["endpoint"] == "awg31.internal:587"
    assert decoded["transport"] == "udp"
    assert decoded["dns"] == "1.1.1.1"
    assert decoded["private_key"] == _credential(device_id, "amneziawg31")["private_key"]
    assert decoded["public_key"] == _credential(device_id, "amneziawg31")["server_public_key"]
    assert decoded["parameters"] == VALID_PARAMETERS
    assert decoded["config"] == config.body


def test_awg31_ui_is_distinct_and_controls_only_awg31_service(
    isolated_stage2,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app import main
    from app.hostd.client import HostdResult

    calls: list[str] = []

    def fake_hostd(command: str, timeout: float = 5) -> HostdResult:
        calls.append(command)
        return HostdResult(
            command=command,
            status="ok",
            message="ok",
            payload={"service": "sg-gateway-awg31.service", "status": "active"},
        )

    monkeypatch.setattr(main, "run_hostd_command", fake_hostd)
    app = main.create_app()
    client = app.test_client()
    _authenticate(client)

    response = client.get("/connections")
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "AmneziaWG 2" in html
    assert "AmneziaWG 3" in html
    assert "AmneziaWG 3.1" in html
    assert "awg31.internal:587" in html
    assert "sg-gateway-awg31.service" in html
    for action in ("start", "stop", "restart", "status"):
        assert f"/connections/amneziawg31/service/{action}" in html
    assert "awg31.status" in calls

    response = client.post("/connections/amneziawg31/service/restart")
    assert response.status_code == 302
    assert calls[-1] == "awg31.restart"


def test_hostd_awg31_actions_target_dedicated_service(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from sg_hostd import awg31_runtime, commands

    calls: list[str] = []

    def fake_control(action: str) -> dict:
        calls.append(action)
        return {
            "ok": True,
            "action": action,
            "service": "sg-gateway-awg31.service",
            "status": "active",
        }

    monkeypatch.setattr(awg31_runtime, "control", fake_control)
    for action in ("start", "stop", "restart", "status"):
        result = commands.execute_command(f"awg31.{action}")
        assert result.status == "ok"
        assert result.payload["service"] == "sg-gateway-awg31.service"
    assert calls == ["start", "stop", "restart", "status"]
