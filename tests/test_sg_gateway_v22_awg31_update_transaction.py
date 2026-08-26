from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path

from app.clients import repository as _repository  # noqa: F401
from app.maintenance.awg31_stage3a import Stage3AInstaller


ROOT = Path(__file__).resolve().parents[1]
WRAPPER = ROOT / "deploy/update-from-github.sh"
CORE = ROOT / "deploy/update-from-github-core.sh"
RUNTIME_SHA256 = {
    "amneziawg-tools-3.0.20260805.tar.gz": "090f9383532822a756d078890b447e00af7f46bd30a10f9f47c46d633d807b19",
    "amneziawg-go-linux-amd64-v3.0.0": "131110027db6d5dc0e35b19eb5b8a2692676081366c34112088dc68bbb050bcd",
    "amneziawg-tools-3.1.20260812.tar.gz": "f18592c499c893b1b87b15de9e707ce265585cf2536698975b6ede8156d14ada",
    "amneziawg-go-linux-amd64-v3.1.20260814": "375bc2645df09498aa30215e3b3a09a97626a8e929f409e0edef6564fb8e3110",
}
SERVICES = (
    "nginx.service",
    "xray.service",
    "mihomo.service",
    "sg-gateway-awg.service",
    "sg-gateway-awg3.service",
    "sg-gateway-awg31.service",
    "sg-gateway-singbox.service",
    "sg-hostd.service",
    "sg-gateway.service",
)


class NoopOS:
    def run(self, *command: str) -> None:
        del command


def _seed_database(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as db:
        db.executescript(
            """
            PRAGMA foreign_keys = ON;
            CREATE TABLE clients (
                id INTEGER PRIMARY KEY, name TEXT NOT NULL, enabled INTEGER NOT NULL DEFAULT 1,
                expires_at TEXT, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE devices (
                id INTEGER PRIMARY KEY, client_id INTEGER NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
                name TEXT NOT NULL, enabled INTEGER NOT NULL DEFAULT 1, expires_at TEXT,
                is_primary INTEGER NOT NULL DEFAULT 0, last_seen_at TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE device_credentials (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                device_id INTEGER NOT NULL REFERENCES devices(id) ON DELETE CASCADE,
                engine TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'pending',
                engine_object_id TEXT, config_json TEXT, rotated_at TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(device_id, engine)
            );
            CREATE TABLE connection_settings (
                engine TEXT PRIMARY KEY, enabled INTEGER NOT NULL DEFAULT 1,
                host TEXT NOT NULL DEFAULT '', port INTEGER NOT NULL DEFAULT 0,
                config_json TEXT NOT NULL DEFAULT '{}',
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            INSERT INTO clients(id, name, created_at) VALUES
              (1, 'alpha', '2026-01-01'), (2, 'beta', '2026-01-01');
            INSERT INTO devices(id, client_id, name, is_primary, created_at) VALUES
              (11, 1, 'main', 1, '2026-01-01'), (22, 2, 'phone', 1, '2026-01-01');
            INSERT INTO connection_settings(engine, host, port, config_json, updated_at)
            VALUES (
              'amneziawg31', 'awg31.internal', 587,
              '{"endpoint":"awg31.internal:587","i1":"<b 0x160301>","i2":"<r 16><t>","i3":"<rd 12>","i4":"<rc 24>","i5":"<b 0x01020304><r 8>","jc":2,"jmin":10,"jmax":20,"s1":1,"s2":2,"s3":3,"s4":4,"h1":"1-2","h2":"3","h3":"4","h4":"5"}',
              '2026-01-01'
            );
            """
        )
        for device_id in (11, 22):
            for engine in ("amneziawg", "amneziawg3"):
                marker = f"{engine}-{device_id}"
                payload = json.dumps(
                    {
                        "marker": marker,
                        "private_key": marker + "-private",
                        "public_key": marker + "-public",
                    },
                    sort_keys=True,
                )
                db.execute(
                    "INSERT INTO device_credentials(device_id, engine, status, engine_object_id, config_json, created_at) "
                    "VALUES (?, ?, 'applied', ?, ?, '2026-01-01')",
                    (device_id, engine, marker, payload),
                )
        existing = json.dumps(
            {
                "profile": "awg31",
                "private_key": "preserved-awg31-private",
                "public_key": "preserved-awg31-public",
                "address": "10.131.0.12/32",
                "endpoint": "awg31.internal:587",
                "transport": "udp",
            },
            sort_keys=True,
        )
        db.execute(
            "INSERT INTO device_credentials(device_id, engine, status, engine_object_id, config_json, created_at) "
            "VALUES (11, 'amneziawg31', 'applied', 'preserved-awg31-public', ?, '2026-01-01')",
            (existing,),
        )


def _credential_rows(database: Path, engines: tuple[str, ...]) -> list[tuple]:
    placeholders = ",".join("?" for _ in engines)
    with sqlite3.connect(database) as db:
        return db.execute(
            f"SELECT id, device_id, engine, status, engine_object_id, config_json, rotated_at, created_at "
            f"FROM device_credentials WHERE engine IN ({placeholders}) ORDER BY id",
            engines,
        ).fetchall()


def _tree_digest(path: Path) -> str:
    digest = hashlib.sha256()
    if not path.exists() and not path.is_symlink():
        return "MISSING"
    for item in [path, *sorted(path.rglob("*"), key=lambda value: value.as_posix())]:
        relative = "." if item == path else item.relative_to(path).as_posix()
        digest.update(relative.encode())
        digest.update(b"\0")
        if item.is_symlink():
            digest.update(b"L" + os.readlink(item).encode())
        elif item.is_file():
            digest.update(b"F" + item.read_bytes())
        elif item.is_dir():
            digest.update(b"D")
        digest.update(b"\0")
    return digest.hexdigest()


def _write_os_fakes(tmp_path: Path) -> tuple[Path, Path, Path]:
    bindir = tmp_path / "os-bin"
    bindir.mkdir()
    service_state = tmp_path / "service-state.json"
    requests = tmp_path / "curl-requests.log"
    initial = {
        service: {
            "active": service in {"nginx.service", "sg-hostd.service", "sg-gateway.service", "sg-gateway-awg3.service"},
            "enabled": service in {"nginx.service", "sg-hostd.service", "sg-gateway.service", "sg-gateway-awg3.service"},
        }
        for service in SERVICES
    }
    service_state.write_text(json.dumps(initial, sort_keys=True))

    systemctl = bindir / "systemctl"
    systemctl.write_text(
        f"""#!{sys.executable}
import json
import os
import sys
from pathlib import Path

path = Path(os.environ["FAKE_SERVICE_STATE"])
state = json.loads(path.read_text())
args = sys.argv[1:]
action = args[0] if args else ""
services = [arg for arg in args[1:] if not arg.startswith("-") and arg not in ("ExecStart",)]

def save():
    path.write_text(json.dumps(state, sort_keys=True))

if action == "show":
    print("{{ path=/usr/bin/waitress-serve ; argv[]=/usr/bin/waitress-serve --call app.production:app ; }}")
elif action in ("is-active", "is-enabled", "is-failed"):
    service = services[-1]
    current = state.get(service, {{"active": False, "enabled": False}})
    if action == "is-failed":
        raise SystemExit(1)
    raise SystemExit(0 if current[action.removeprefix("is-")] else 1)
elif action == "daemon-reload" or action == "reload" or action == "try-restart":
    pass
elif action in ("start", "restart", "stop", "enable", "disable"):
    for service in services:
        current = state.setdefault(service, {{"active": False, "enabled": False}})
        if action == "restart" and service == "sg-gateway-awg31.service" and os.environ.get("FAIL_AWG31") == "1":
            print("injected Stage3A service failure", file=sys.stderr)
            raise SystemExit(77)
        if action in ("start", "restart"):
            current["active"] = True
        elif action == "stop":
            current["active"] = False
        elif action == "enable":
            current["enabled"] = True
        elif action == "disable":
            current["enabled"] = False
            if "--now" in args:
                current["active"] = False
    save()
else:
    print("unsupported fake systemctl call: " + " ".join(args), file=sys.stderr)
    raise SystemExit(64)
"""
    )
    systemctl.chmod(0o755)

    curl = bindir / "curl"
    curl.write_text(
        """#!/usr/bin/env bash
set -euo pipefail
url=""
output=""
while (($#)); do
  case "$1" in
    -o) output=$2; shift 2 ;;
    -*) shift ;;
    *) url=$1; shift ;;
  esac
done
printf '%s\n' "$url" >> "$FAKE_CURL_LOG"
if [[ -n $output && $url == *update-from-github-core.sh ]]; then
  cp "$TEST_CORE_SCRIPT" "$output"
fi
"""
    )
    curl.chmod(0o755)

    runuser = bindir / "runuser"
    runuser.write_text(
        """#!/usr/bin/env bash
set -euo pipefail
while (($#)) && [[ $1 != -- ]]; do shift; done
[[ ${1:-} == -- ]] && shift
exec "$@"
"""
    )
    runuser.chmod(0o755)
    fake_id = bindir / "id"
    fake_id.write_text(
        "#!/usr/bin/env bash\n"
        "if [[ ${1:-} == -u ]]; then printf '0\\n'; exit 0; fi\n"
        "exec /usr/bin/id \"$@\"\n"
    )
    fake_id.chmod(0o755)
    for name in ("chown", "nginx", "sleep"):
        fake = bindir / name
        fake.write_text("#!/usr/bin/env bash\nexit 0\n")
        fake.chmod(0o755)
    return bindir, service_state, requests


def _prepare_server(tmp_path: Path) -> tuple[Path, Path]:
    server_root = tmp_path / "server-root"
    prefix = server_root / "opt/sg-gateway"
    for directory in ("app", "hostd", "deploy"):
        shutil.copytree(ROOT / directory, prefix / directory)
    for filename in ("VERSION", "requirements.txt"):
        shutil.copy2(ROOT / filename, prefix / filename)
    assets = prefix / "assets/geoip"
    assets.mkdir(parents=True)
    (assets / "sg-country-geoip.dat").write_bytes(b"preserved-country-asset")
    (prefix / ".venv").symlink_to(Path(sys.executable).parents[1])

    config = server_root / "etc/sg-gateway"
    config.mkdir(parents=True)
    (config / "runtime.env").write_text("SG_GATEWAY_PANEL_PORT=63443\n")
    (config / "sg-gateway.env").write_text("SECRET_KEY=test-transaction\n")
    tls = server_root / "var/lib/sg-gateway/security/tls-state.json"
    tls.parent.mkdir(parents=True)
    tls.write_text('{"https_ready":false,"public_port":63443}\n')

    for relative, content in (
        ("etc/amnezia/amneziawg/awg0.conf", b"awg2-config-byte-for-byte"),
        ("etc/amnezia/amneziawg/awg3.conf", b"awg3-config-byte-for-byte"),
        ("etc/systemd/system/sg-gateway.service", b"ExecStart=/usr/bin/waitress-serve --call app.production:app\n"),
        ("etc/systemd/system/sg-hostd.service", b"hostd-unit-byte-for-byte"),
        ("etc/systemd/system/sg-gateway-awg.service", b"awg2-unit-byte-for-byte"),
        ("etc/systemd/system/sg-gateway-awg3.service", b"awg3-unit-byte-for-byte"),
        ("etc/nginx/nginx.conf", b"nginx-byte-for-byte"),
        ("etc/nginx/sites-available/sg-gateway", b"available-byte-for-byte"),
        ("etc/nginx/sites-enabled/sg-gateway", b"enabled-byte-for-byte"),
        ("etc/nginx/stream-conf.d/sg-gateway-443.conf", b"stream-byte-for-byte"),
    ):
        path = server_root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)

    database = server_root / "var/lib/sg-gateway/sg-gateway.sqlite"
    _seed_database(database)

    # Seed the already-supported AWG3 runtime with the exact Stage3A build,
    # then remove all AWG31 artifacts so the update must create them.
    Stage3AInstaller(source_root=ROOT, root=server_root, os_boundary=NoopOS()).migrate(
        database=database
    )
    with sqlite3.connect(database) as db:
        db.execute("DELETE FROM device_credentials WHERE device_id = 22 AND engine = 'amneziawg31'")
        db.execute(
            "UPDATE connection_settings SET config_json = ?, updated_at = '2026-01-01' WHERE engine = 'amneziawg31'",
            (
                '{"endpoint":"awg31.internal:587","i1":"<b 0x160301>","i2":"<r 16><t>","i3":"<rd 12>","i4":"<rc 24>","i5":"<b 0x01020304><r 8>","jc":2,"jmin":10,"jmax":20,"s1":1,"s2":2,"s3":3,"s4":4,"h1":"1-2","h2":"3","h3":"4","h4":"5"}',
            ),
        )
        db.commit()
    for path in (
        prefix / "awg31",
        server_root / "etc/amnezia/amneziawg/awg31",
        server_root / "var/lib/sg-gateway/awg31",
        server_root / "etc/systemd/system/sg-gateway-awg31.service",
    ):
        if path.is_dir():
            shutil.rmtree(path)
        else:
            path.unlink(missing_ok=True)
    return server_root, database


def _run_public_update(
    tmp_path: Path,
    *,
    server_root: Path,
    bindir: Path,
    service_state: Path,
    requests: Path,
    fail_stage3a: bool,
) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env.update(
        {
            "PATH": f"{bindir}:{env['PATH']}",
            "TMPDIR": str(tmp_path / "tmp"),
            "FAKE_SERVICE_STATE": str(service_state),
            "FAKE_CURL_LOG": str(requests),
            "TEST_CORE_SCRIPT": str(CORE),
            "FAIL_AWG31": "1" if fail_stage3a else "0",
            "SG_GATEWAY_ROOT": str(server_root),
            "SG_GATEWAY_GITHUB_BRANCH": subprocess.check_output(
                ["git", "branch", "--show-current"], cwd=ROOT, text=True
            ).strip(),
            "SG_GATEWAY_GIT_URL": f"file://{ROOT}",
            "SG_GATEWAY_RAW_BASE_URL": "https://raw.test.invalid/s-gor/sg-gateway-v22",
            "SG_GATEWAY_UPDATE_BACKUP_ROOT": str(server_root / "root/update-safety"),
            "SG_GATEWAY_UPDATE_BACKUP_HEADROOM_MB": "0",
        }
    )
    Path(env["TMPDIR"]).mkdir(exist_ok=True)
    return subprocess.run(
        ["bash"],
        input=WRAPPER.read_text(),
        cwd=tmp_path,
        env=env,
        text=True,
        capture_output=True,
        check=False,
        timeout=180,
    )


def _service_snapshot(path: Path) -> dict:
    state = json.loads(path.read_text())
    return {service: state[service] for service in SERVICES}


def test_public_update_is_atomic_credentials_safe_and_idempotent(tmp_path: Path) -> None:
    bindir, service_state, requests = _write_os_fakes(tmp_path)
    server_root, database = _prepare_server(tmp_path)
    prefix = server_root / "opt/sg-gateway"
    legacy_before = _credential_rows(database, ("amneziawg", "amneziawg3"))
    awg31_existing_before = _credential_rows(database, ("amneziawg31",))
    database_before = database.read_bytes()
    preserved_runtime_before = {
        "awg2_config": (server_root / "etc/amnezia/amneziawg/awg0.conf").read_bytes(),
        "awg3_config": (server_root / "etc/amnezia/amneziawg/awg3.conf").read_bytes(),
        "awg3_runtime": _tree_digest(prefix / "awg3"),
    }
    rollback_before = {
        "source": _tree_digest(prefix),
        "etc_config": _tree_digest(server_root / "etc/sg-gateway"),
        "awg_configs": _tree_digest(server_root / "etc/amnezia/amneziawg"),
        "nginx": _tree_digest(server_root / "etc/nginx"),
        "units": _tree_digest(server_root / "etc/systemd/system"),
        "services": _service_snapshot(service_state),
    }

    failed = _run_public_update(
        tmp_path,
        server_root=server_root,
        bindir=bindir,
        service_state=service_state,
        requests=requests,
        fail_stage3a=True,
    )
    assert failed.returncode != 0
    assert "AWG31 Stage3A migration внутри Update transaction" in failed.stdout
    assert "ROLLBACK OK" in failed.stdout
    assert database.read_bytes() == database_before
    assert _tree_digest(prefix) == rollback_before["source"]
    assert _tree_digest(server_root / "etc/sg-gateway") == rollback_before["etc_config"]
    assert _tree_digest(server_root / "etc/amnezia/amneziawg") == rollback_before["awg_configs"]
    assert _tree_digest(server_root / "etc/nginx") == rollback_before["nginx"]
    assert _tree_digest(server_root / "etc/systemd/system") == rollback_before["units"]
    assert _service_snapshot(service_state) == rollback_before["services"]
    assert _credential_rows(database, ("amneziawg", "amneziawg3")) == legacy_before
    assert _credential_rows(database, ("amneziawg31",)) == awg31_existing_before
    assert not (prefix / "awg31").exists()
    assert not (server_root / "etc/amnezia/amneziawg/awg31").exists()
    assert not (server_root / "var/lib/sg-gateway/awg31").exists()
    assert not (server_root / "etc/systemd/system/sg-gateway-awg31.service").exists()

    succeeded = _run_public_update(
        tmp_path,
        server_root=server_root,
        bindir=bindir,
        service_state=service_state,
        requests=requests,
        fail_stage3a=False,
    )
    assert succeeded.returncode == 0, succeeded.stderr
    assert "Source mode: LIGHT" in succeeded.stdout
    assert "Stage3A runtime staging: 4 verified files" in succeeded.stdout
    assert "Credentials transition: preserved=5 added_awg31=1" in succeeded.stdout
    assert _credential_rows(database, ("amneziawg", "amneziawg3")) == legacy_before
    awg31_after_first = _credential_rows(database, ("amneziawg31",))
    assert len(awg31_after_first) == 2
    before_existing = awg31_existing_before[0]
    after_existing = awg31_after_first[0]
    assert after_existing[:3] == before_existing[:3]
    assert after_existing[4] == before_existing[4]
    assert after_existing[6:] == before_existing[6:]
    before_config = json.loads(before_existing[5])
    after_config = json.loads(after_existing[5])
    for protected in ("private_key", "public_key", "address"):
        assert after_config[protected] == before_config[protected]
    assert after_config["server_public_key"]
    assert (server_root / "etc/amnezia/amneziawg/awg0.conf").read_bytes() == preserved_runtime_before["awg2_config"]
    assert (server_root / "etc/amnezia/amneziawg/awg3.conf").read_bytes() == preserved_runtime_before["awg3_config"]
    assert _tree_digest(prefix / "awg3") == preserved_runtime_before["awg3_runtime"]
    vendor = prefix / "vendor/cores"
    assert sorted(path.name for path in vendor.iterdir()) == sorted(RUNTIME_SHA256)
    assert {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in vendor.iterdir()
    } == RUNTIME_SHA256

    repeated = _run_public_update(
        tmp_path,
        server_root=server_root,
        bindir=bindir,
        service_state=service_state,
        requests=requests,
        fail_stage3a=False,
    )
    assert repeated.returncode == 0, repeated.stderr
    assert "Credentials transition: preserved=6 added_awg31=0" in repeated.stdout
    assert _credential_rows(database, ("amneziawg31",)) == awg31_after_first
    assert _credential_rows(database, ("amneziawg", "amneziawg3")) == legacy_before
    assert (server_root / "etc/amnezia/amneziawg/awg0.conf").read_bytes() == preserved_runtime_before["awg2_config"]
    assert (server_root / "etc/amnezia/amneziawg/awg3.conf").read_bytes() == preserved_runtime_before["awg3_config"]
    assert _tree_digest(prefix / "awg3") == preserved_runtime_before["awg3_runtime"]
    curl_requests = requests.read_text().splitlines()
    assert any("/deploy/update-from-github-core.sh" in request for request in curl_requests)
