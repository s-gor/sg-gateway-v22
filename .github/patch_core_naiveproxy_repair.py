from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path

CORE = Path("deploy/update-from-github-core.sh")
TEST = Path("tests/test_naiveproxy_core_update_repair_02208.py")
WORKFLOW = Path(".github/workflows/patch-core-naiveproxy-repair.yml")
SELF = Path(".github/patch_core_naiveproxy_repair.py")

body = CORE.read_text(encoding="utf-8")
required = [
    'NAIVE_SERVICE="sg-gateway-naiveproxy.service"',
    'NAIVE_ROOT="$PREFIX/naiveproxy"',
    "/hostd/systemd/",
    '".venv"|"awg3"|"naiveproxy"',
    '-o -path "$NAIVE_ROOT"',
    'sg-gateway-singbox.service "$NAIVE_SERVICE"',
]
missing = [item for item in required if item not in body]
if missing:
    raise SystemExit(f"core preservation prerequisites missing: {missing!r}")

if "repair_naiveproxy_runtime_if_needed() {" not in body:
    helper = r'''naiveproxy_profile_present() {
  [[ -f "$DATABASE" ]] || return 1
  "$PREFIX/.venv/bin/python" -B - "$DATABASE" <<'PYNAIVEPROFILE'
import sqlite3
import sys

connection = sqlite3.connect(f"file:{sys.argv[1]}?mode=ro", uri=True)
try:
    tables = {
        str(row[0])
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    count = 0
    if "connection_settings" in tables:
        count += int(connection.execute(
            "SELECT COUNT(*) FROM connection_settings WHERE engine='naiveproxy'"
        ).fetchone()[0])
    if "device_credentials" in tables:
        count += int(connection.execute(
            "SELECT COUNT(*) FROM device_credentials WHERE engine='naiveproxy'"
        ).fetchone()[0])
finally:
    connection.close()
raise SystemExit(0 if count else 1)
PYNAIVEPROFILE
}

repair_naiveproxy_runtime_if_needed() {
  [[ "$SYSTEM_ROOT" == / ]] || return 0
  [[ -x "$NAIVE_ROOT/bin/caddy" ]] && return 0
  naiveproxy_profile_present || return 0
  [[ -f "$PREFIX/deploy/install-naiveproxy.sh" ]] || fail "NaiveProxy runtime is missing and installer is unavailable"
  [[ -f "$PREFIX/deploy/$NAIVE_SERVICE" ]] || fail "NaiveProxy runtime is missing and service source is unavailable"
  [[ -f "$PREFIX/hostd/systemd/$HOSTD_SERVICE" ]] || fail "NaiveProxy runtime is missing and hostd systemd source is unavailable"

  printf '[SG-Gateway Update] NaiveProxy profile exists but runtime is missing; repairing pinned runtime...\n'
  SG_GATEWAY_SOURCE_ROOT="$PREFIX" \
  SG_GATEWAY_UPDATE_BRANCH="$BRANCH" \
    bash "$PREFIX/deploy/install-naiveproxy.sh"
  [[ -x "$NAIVE_ROOT/bin/caddy" ]] || fail "NaiveProxy runtime repair did not install caddy"
  printf '[SG-Gateway Update] NaiveProxy runtime repaired: OK\n'
}

'''
    marker = "prepare_preserved_assets() {\n"
    if body.count(marker) != 1:
        raise SystemExit("prepare_preserved_assets marker mismatch")
    body = body.replace(marker, helper + marker, 1)

call = "  migrate_panel_wsgi_service\n  repair_naiveproxy_runtime_if_needed\n}\n\nrestart_panel() {"
if call not in body:
    old = "  migrate_panel_wsgi_service\n}\n\nrestart_panel() {"
    if body.count(old) != 1:
        raise SystemExit("deploy_source tail marker mismatch")
    body = body.replace(old, call, 1)
CORE.write_text(body, encoding="utf-8")

checks = [
    "/hostd/systemd/",
    '".venv"|"awg3"|"naiveproxy"',
    'NAIVE_ROOT="$PREFIX/naiveproxy"',
    'sg-gateway-singbox.service "$NAIVE_SERVICE"',
    "repair_naiveproxy_runtime_if_needed",
    "naiveproxy_profile_present",
    'SG_GATEWAY_SOURCE_ROOT="$PREFIX"',
    'bash "$PREFIX/deploy/install-naiveproxy.sh"',
    '[[ "$SYSTEM_ROOT" == / ]] || return 0',
    '-o -path "$NAIVE_ROOT"',
]
patched = CORE.read_text(encoding="utf-8")
missing_checks = [item for item in checks if item not in patched]
if missing_checks:
    raise SystemExit(f"patched core contract missing: {missing_checks!r}")
subprocess.run(["bash", "-n", str(CORE)], check=True)

TEST.write_text(
    '''from pathlib import Path\n\n\ndef test_core_update_preserves_and_repairs_naiveproxy_runtime():\n    source = Path("deploy/update-from-github-core.sh").read_text(encoding="utf-8")\n    assert "/hostd/systemd/" in source\n    assert '\".venv\"|\"awg3\"|\"naiveproxy\"' in source\n    assert 'NAIVE_ROOT="$PREFIX/naiveproxy"' in source\n    assert 'sg-gateway-singbox.service "$NAIVE_SERVICE"' in source\n    assert "repair_naiveproxy_runtime_if_needed" in source\n    assert "naiveproxy_profile_present" in source\n    assert 'SG_GATEWAY_SOURCE_ROOT="$PREFIX"' in source\n    assert 'bash "$PREFIX/deploy/install-naiveproxy.sh"' in source\n    assert '[[ "$SYSTEM_ROOT" == / ]] || return 0' in source\n\n\ndef test_core_update_protects_naiveproxy_from_permission_rewrite():\n    source = Path("deploy/update-from-github-core.sh").read_text(encoding="utf-8")\n    assert '-o -path "$NAIVE_ROOT"' in source\n''',
    encoding="utf-8",
)
compile(TEST.read_text(encoding="utf-8"), str(TEST), "exec")

WORKFLOW.unlink(missing_ok=True)
SELF.unlink(missing_ok=True)

tracked = subprocess.check_output(["git", "ls-files"], text=True).splitlines()
tracked = [p for p in tracked if p != "SOURCE-SHA256SUMS" and Path(p).exists()]
rows = [f"{hashlib.sha256(Path(p).read_bytes()).hexdigest()}  {p}" for p in sorted(tracked)]
Path("SOURCE-SHA256SUMS").write_text("\n".join(rows) + "\n", encoding="utf-8")

subprocess.run(["git", "config", "user.name", "github-actions[bot]"], check=True)
subprocess.run(["git", "config", "user.email", "41898282+github-actions[bot]@users.noreply.github.com"], check=True)
subprocess.run(["git", "add", "-A"], check=True)
subprocess.run(["git", "commit", "-m", "fix: repair missing NaiveProxy runtime in core update"], check=True)
subprocess.run(["git", "push", "origin", "HEAD:fix/02208-clients-keys-dormant-restore"], check=True)
