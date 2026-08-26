#!/usr/bin/env bash
set -Eeuo pipefail
# SG_GATEWAY_UPDATE_CORE

REPOSITORY="${SG_GATEWAY_GITHUB_REPOSITORY:-s-gor/sg-gateway-v22}"
BRANCH="${SG_GATEWAY_GITHUB_BRANCH:-${SG_GATEWAY_UPDATE_BRANCH:-main}}"
ARCHIVE_URL="https://github.com/${REPOSITORY}/archive/refs/heads/${BRANCH}.tar.gz"
GIT_URL="${SG_GATEWAY_GIT_URL:-https://github.com/${REPOSITORY}.git}"

SYSTEM_ROOT="${SG_GATEWAY_ROOT:-/}"
SYSTEM_ROOT="${SYSTEM_ROOT%/}"
[[ -n "$SYSTEM_ROOT" ]] || SYSTEM_ROOT="/"

system_path() {
  local path="$1"
  [[ "$path" == /* ]] || return 1
  if [[ "$SYSTEM_ROOT" == / ]]; then
    printf '%s\n' "$path"
  else
    printf '%s%s\n' "$SYSTEM_ROOT" "$path"
  fi
}

PREFIX="${SG_GATEWAY_PREFIX:-$(system_path /opt/sg-gateway)}"
CONFIG_DIR="${SG_GATEWAY_CONFIG_DIR:-$(system_path /etc/sg-gateway)}"
DATA_DIR="${SG_GATEWAY_DATA_DIR:-$(system_path /var/lib/sg-gateway)}"
DATABASE="${SG_GATEWAY_DATABASE:-$DATA_DIR/sg-gateway.sqlite}"
BACKUP_ROOT="${SG_GATEWAY_UPDATE_BACKUP_ROOT:-$(system_path /root/sg-gateway-update-safety)}"
BACKUP_KEEP="${SG_GATEWAY_UPDATE_BACKUP_KEEP:-2}"
BACKUP_HEADROOM_MB="${SG_GATEWAY_UPDATE_BACKUP_HEADROOM_MB:-256}"
PANEL_SERVICE="sg-gateway.service"
PANEL_PRODUCTION_WSGI="app.production:app"
HOSTD_SERVICE="sg-hostd.service"
AWG3_SERVICE="sg-gateway-awg3.service"
AWG31_SERVICE="sg-gateway-awg31.service"
AWG2_CONFIG="$(system_path /etc/amnezia/amneziawg/awg0.conf)"
AWG2_UNIT="$(system_path /etc/systemd/system/sg-gateway-awg.service)"
AWG3_CONFIG="$(system_path /etc/amnezia/amneziawg/awg3.conf)"
AWG3_UNIT="$(system_path /etc/systemd/system/sg-gateway-awg3.service)"
AWG31_CONFIG="$(system_path /etc/amnezia/amneziawg/awg31)"
AWG31_STATE="$(system_path /var/lib/sg-gateway/awg31)"
AWG31_UNIT="$(system_path /etc/systemd/system/sg-gateway-awg31.service)"
AWG3_ROOT="$PREFIX/awg3"
LETSENCRYPT_DIR="$(system_path /etc/letsencrypt)"
NGINX_CONFIG="$(system_path /etc/nginx/nginx.conf)"
NGINX_SITE_AVAILABLE="$(system_path /etc/nginx/sites-available/sg-gateway)"
NGINX_SITE_ENABLED="$(system_path /etc/nginx/sites-enabled/sg-gateway)"
NGINX_STREAM_CONFIG="$(system_path /etc/nginx/stream-conf.d/sg-gateway-443.conf)"
PANEL_UNIT="$(system_path /etc/systemd/system/sg-gateway.service)"
HOSTD_UNIT="$(system_path /etc/systemd/system/sg-hostd.service)"
TEMP_DIR=""
BACKUP_DIR=""
SOURCE_DIR=""
SOURCE_COMMIT="${SG_GATEWAY_SOURCE_COMMIT:-}"
MIGRATION_SOURCE_DIR=""
PANEL_UPDATE_STATE="${SG_GATEWAY_PANEL_UPDATE_STATE:-$DATA_DIR/updates/panel-state.json}"
BACKUP_READY=0
SERVICES_STOPPED=0
UPDATE_FINISHED=0
ASSETS_FINGERPRINT=""
ASSETS_RECOVERY_DIR=""
ASSETS_RECOVERY_SOURCE=""

RUNTIME_FILES=(
  amneziawg-tools-3.0.20260805.tar.gz
  amneziawg-go-linux-amd64-v3.0.0
  amneziawg-tools-3.1.20260812.tar.gz
  amneziawg-go-linux-amd64-v3.1.20260814
)
RUNTIME_SHA256=(
  090f9383532822a756d078890b447e00af7f46bd30a10f9f47c46d633d807b19
  131110027db6d5dc0e35b19eb5b8a2692676081366c34112088dc68bbb050bcd
  f18592c499c893b1b87b15de9e707ce265585cf2536698975b6ede8156d14ada
  375bc2645df09498aa30215e3b3a09a97626a8e929f409e0edef6564fb8e3110
)

GREEN=$'\033[1;32m'
RED=$'\033[1;31m'
YELLOW=$'\033[1;33m'
CYAN=$'\033[1;36m'
RESET=$'\033[0m'

fail() {
  printf '%s[SG-Gateway Update] ERROR:%s %s\n' "$RED" "$RESET" "$*" >&2
  return 1
}

cleanup() {
  if [[ -n "$TEMP_DIR" && -d "$TEMP_DIR" ]]; then
    rm -rf "$TEMP_DIR"
  fi
}


# SG_GATEWAY_02205_SAFETY_BACKUP_DISK_GUARD_V1
validate_backup_policy() {
  [[ "$BACKUP_KEEP" =~ ^[0-9]+$ ]] || fail "SG_GATEWAY_UPDATE_BACKUP_KEEP must be an integer"
  (( BACKUP_KEEP >= 1 )) || fail "SG_GATEWAY_UPDATE_BACKUP_KEEP must be at least 1"
  [[ "$BACKUP_HEADROOM_MB" =~ ^[0-9]+$ ]] || fail "SG_GATEWAY_UPDATE_BACKUP_HEADROOM_MB must be a non-negative integer"
}

backup_is_complete() {
  local dir="$1"
  [[ -d "$dir" ]] || return 1
  [[ -f "$dir/state.tar" && -f "$dir/existing-paths.txt" && -f "$dir/service-state.tsv" ]] || return 1
  tar -tf "$dir/state.tar" >/dev/null 2>&1
}

cleanup_incomplete_safety_backups() {
  local dir listing
  [[ -d "$BACKUP_ROOT" ]] || return 0
  listing="$(mktemp "$BACKUP_ROOT/.cleanup-incomplete.XXXXXX")"
  find "$BACKUP_ROOT" -mindepth 1 -maxdepth 1 -type d -name '*-before-update' -print 2>/dev/null | sort > "$listing"
  while IFS= read -r dir; do
    [[ -n "$dir" ]] || continue
    [[ -n "$BACKUP_DIR" && "$dir" == "$BACKUP_DIR" ]] && continue
    if ! backup_is_complete "$dir"; then
      printf '[SG-Gateway Update] Removing incomplete Safety Backup: %s\n' "$(basename "$dir")"
      rm -rf -- "$dir"
    fi
  done < "$listing"
  rm -f -- "$listing"
}

prune_safety_backups() {
  local keep="$1" kept=0 dir listing
  [[ "$keep" =~ ^[0-9]+$ ]] || return 1
  [[ -d "$BACKUP_ROOT" ]] || return 0
  listing="$(mktemp "$BACKUP_ROOT/.prune.XXXXXX")"
  find "$BACKUP_ROOT" -mindepth 1 -maxdepth 1 -type d -name '*-before-update' -print 2>/dev/null | sort -r > "$listing"
  while IFS= read -r dir; do
    [[ -n "$dir" ]] || continue
    backup_is_complete "$dir" || continue
    if (( kept < keep )); then
      ((kept += 1))
      continue
    fi
    printf '[SG-Gateway Update] Pruning old Safety Backup: %s\n' "$(basename "$dir")"
    rm -rf -- "$dir" || return 1
  done < "$listing"
  rm -f -- "$listing"
}

remove_current_incomplete_backup() {
  (( BACKUP_READY == 0 )) || return 0
  [[ -n "$BACKUP_DIR" && -d "$BACKUP_DIR" ]] || return 0
  case "$BACKUP_DIR" in
    "$BACKUP_ROOT"/*-before-update)
      printf '[SG-Gateway Update] Removing failed partial Safety Backup: %s\n' "$(basename "$BACKUP_DIR")" >&2
      rm -rf -- "$BACKUP_DIR"
      ;;
    *)
      printf '[SG-Gateway Update] Refusing unsafe partial-backup cleanup path: %s\n' "$BACKUP_DIR" >&2
      return 1
      ;;
  esac
}

ensure_safety_backup_space() {
  local probe_env="$BACKUP_DIR/space-preflight-https.env"
  local probe_paths="$BACKUP_DIR/space-preflight-protected.txt"
  local candidate kept_path covered size_kb available_kb
  local payload_kb=0
  local candidates=()
  local unique=()
  local filtered=()

  https_state > "$probe_env"
  protected_runtime_paths "$probe_env" "$probe_paths"

  candidates+=(
    "$PREFIX"
    "$CONFIG_DIR"
    "$DATA_DIR"
    "$LETSENCRYPT_DIR"
    "$AWG2_CONFIG"
    "$AWG2_UNIT"
    "$AWG3_CONFIG"
    "$AWG3_UNIT"
    "$AWG31_CONFIG"
    "$AWG31_STATE"
    "$AWG31_UNIT"
    "$NGINX_CONFIG"
    "$NGINX_SITE_AVAILABLE"
    "$NGINX_SITE_ENABLED"
    "$NGINX_STREAM_CONFIG"
    "$PANEL_UNIT"
    "$HOSTD_UNIT"
  )
  while IFS= read -r candidate; do
    [[ -n "$candidate" ]] && candidates+=("$candidate")
  done < "$probe_paths"

  for candidate in "${candidates[@]}"; do
    [[ "$candidate" == /* ]] || continue
    candidate="${candidate%/}"
    [[ -e "$candidate" || -L "$candidate" ]] || continue
    covered=0
    for kept_path in "${unique[@]}"; do
      if [[ "$candidate" == "$kept_path" || "$candidate" == "$kept_path/"* ]]; then
        covered=1
        break
      fi
    done
    (( covered == 1 )) && continue
    filtered=()
    for kept_path in "${unique[@]}"; do
      [[ "$kept_path" == "$candidate/"* ]] && continue
      filtered+=("$kept_path")
    done
    unique=("${filtered[@]}" "$candidate")
  done

  for candidate in "${unique[@]}"; do
    size_kb="$(du -sk --apparent-size -- "$candidate" 2>/dev/null | awk 'NR==1 {print $1}')"
    [[ "$size_kb" =~ ^[0-9]+$ ]] || fail "cannot estimate Safety Backup size for $candidate"
    ((payload_kb += size_kb))
  done

  available_kb="$(df -Pk "$BACKUP_ROOT" | awk 'NR==2 {print $4}')"
  [[ "$available_kb" =~ ^[0-9]+$ ]] || fail "cannot determine free disk space for Safety Backup"

  local headroom_kb=$(( BACKUP_HEADROOM_MB * 1024 ))
  local required_kb=$(( payload_kb + headroom_kb ))
  local payload_mb=$(( (payload_kb + 1023) / 1024 ))
  local available_mb=$(( available_kb / 1024 ))
  local required_mb=$(( (required_kb + 1023) / 1024 ))

  printf '[SG-Gateway Update] Safety Backup disk preflight: payload ~%s MiB; free %s MiB; required with reserve %s MiB.\n' \
    "$payload_mb" "$available_mb" "$required_mb"
  (( available_kb >= required_kb )) || \
    fail "not enough free disk space for Safety Backup: need about ${required_mb} MiB, free ${available_mb} MiB"

  rm -f -- "$probe_env" "$probe_paths"
}

env_value() {
  local file="$1" key="$2"
  python3 - "$file" "$key" <<'PYENV'
import shlex
import sys
from pathlib import Path

path = Path(sys.argv[1])
key = sys.argv[2]
try:
    lines = path.read_text(encoding="utf-8").splitlines()
except OSError:
    raise SystemExit(1)
for raw in lines:
    line = raw.strip()
    if not line or line.startswith("#") or "=" not in line:
        continue
    name, value = line.split("=", 1)
    if name.strip() != key:
        continue
    value = value.strip()
    if value[:1] in {'"', "'"}:
        try:
            parsed = shlex.split(value, posix=True)
            value = parsed[0] if parsed else ""
        except ValueError:
            value = value[1:-1] if len(value) >= 2 else ""
    print(value)
    raise SystemExit(0)
raise SystemExit(1)
PYENV
}

fingerprint_paths() {
  python3 - "$@" <<'PYFP'
import hashlib
import os
import stat
import sys
from pathlib import Path

digest = hashlib.sha256()
for raw_root in sys.argv[1:]:
    root = Path(raw_root)
    digest.update(str(root).encode())
    digest.update(b"\0")
    if not root.exists() and not root.is_symlink():
        digest.update(b"MISSING\0")
        continue
    paths = [root]
    if root.is_dir() and not root.is_symlink():
        paths.extend(sorted(root.rglob("*"), key=lambda p: p.as_posix()))
    for path in paths:
        try:
            info = path.lstat()
        except OSError as exc:
            raise SystemExit(f"cannot stat {path}: {exc}")
        digest.update(path.as_posix().encode())
        digest.update(b"\0")
        digest.update(oct(stat.S_IMODE(info.st_mode)).encode())
        digest.update(b"\0")
        if stat.S_ISLNK(info.st_mode):
            digest.update(b"L")
            digest.update(os.readlink(path).encode())
        elif stat.S_ISREG(info.st_mode):
            digest.update(b"F")
            try:
                with path.open("rb") as stream:
                    for block in iter(lambda: stream.read(1024 * 1024), b""):
                        digest.update(block)
            except OSError as exc:
                raise SystemExit(f"cannot read {path}: {exc}")
        elif stat.S_ISDIR(info.st_mode):
            digest.update(b"D")
        else:
            digest.update(b"O")
        digest.update(b"\0")
print(digest.hexdigest())
PYFP
}

fingerprint_tree_relative() {
  python3 - "$1" <<'PYASSETFP'
import hashlib
import os
import sys
from pathlib import Path

root = Path(sys.argv[1])
if not root.is_dir():
    raise SystemExit(1)
digest = hashlib.sha256()
for path in sorted(root.rglob("*"), key=lambda p: p.relative_to(root).as_posix()):
    rel = path.relative_to(root).as_posix()
    digest.update(rel.encode("utf-8"))
    digest.update(b"\0")
    if path.is_symlink():
        digest.update(b"L")
        digest.update(os.readlink(path).encode("utf-8"))
    elif path.is_file():
        digest.update(b"F")
        with path.open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(block)
    elif path.is_dir():
        digest.update(b"D")
    digest.update(b"\0")
print(digest.hexdigest())
PYASSETFP
}

fingerprint_clients() {
  python3 - "$DATA_DIR/sg-gateway.sqlite" <<'PYCLIENTS'
import hashlib
import json
import sqlite3
import sys
from pathlib import Path

path = Path(sys.argv[1])
if not path.is_file():
    print("NO_DATABASE")
    raise SystemExit(0)

con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
con.row_factory = sqlite3.Row
payload = {}
try:
    for table in ("clients", "devices", "device_credentials"):
        try:
            rows = con.execute(f"SELECT * FROM {table} ORDER BY 1,2").fetchall()
        except sqlite3.Error:
            rows = []
        cleaned = []
        for row in rows:
            item = dict(row)
            if table == "device_credentials" and item.get("config_json"):
                try:
                    cfg = json.loads(item["config_json"])
                except Exception:
                    cfg = {}
                def keep(value):
                    if isinstance(value, dict):
                        wanted = {
                            "uuid", "id", "private_key", "public_key", "password",
                            "username", "address", "auth", "token", "short_id",
                            "endpoint", "host", "port",
                        }
                        return {
                            key: keep(val)
                            for key, val in sorted(value.items())
                            if key.lower() in wanted
                        }
                    if isinstance(value, list):
                        return [keep(v) for v in value]
                    return value
                item["config_json"] = keep(cfg)
            cleaned.append(item)
        payload[table] = cleaned
finally:
    con.close()

raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
print(hashlib.sha256(raw).hexdigest())
PYCLIENTS
}

capture_credentials_state() {
  local output="$1"
  python3 - "$DATABASE" "$output" <<'PYCREDENTIALSNAPSHOT'
import base64
import json
import sqlite3
import sys
from pathlib import Path

database = Path(sys.argv[1])
output = Path(sys.argv[2])

def encode(value):
    if value is None:
        return {"type": "null"}
    if isinstance(value, bytes):
        return {"type": "blob", "value": base64.b64encode(value).decode("ascii")}
    if isinstance(value, int):
        return {"type": "integer", "value": value}
    if isinstance(value, float):
        return {"type": "real", "value": repr(value)}
    return {"type": "text", "value": str(value)}

payload = {"tables": {}}
with sqlite3.connect(f"file:{database}?mode=ro", uri=True) as connection:
    for table in ("clients", "devices", "device_credentials"):
        columns = [row[1] for row in connection.execute(f"PRAGMA table_info({table})")]
        if not columns:
            raise SystemExit(f"required credentials table is missing: {table}")
        order = ", ".join(f'"{column}"' for column in columns)
        rows = connection.execute(f'SELECT {order} FROM "{table}" ORDER BY {order}').fetchall()
        payload["tables"][table] = {
            "columns": columns,
            "rows": [[encode(value) for value in row] for row in rows],
        }

temporary = output.with_name(output.name + ".new")
temporary.write_text(json.dumps(payload, sort_keys=True, separators=(",", ":")), encoding="utf-8")
temporary.replace(output)
PYCREDENTIALSNAPSHOT
}

verify_credentials_transition() {
  local before="$1"
  python3 - "$DATABASE" "$before" <<'PYCREDENTIALVERIFY'
import base64
import json
import sqlite3
import sys
from collections import Counter
from pathlib import Path

database = Path(sys.argv[1])
before = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))

def encode(value):
    if value is None:
        return {"type": "null"}
    if isinstance(value, bytes):
        return {"type": "blob", "value": base64.b64encode(value).decode("ascii")}
    if isinstance(value, int):
        return {"type": "integer", "value": value}
    if isinstance(value, float):
        return {"type": "real", "value": repr(value)}
    return {"type": "text", "value": str(value)}

def decode(value):
    kind = value["type"]
    if kind == "null":
        return None
    if kind == "blob":
        return base64.b64decode(value["value"])
    if kind == "integer":
        return int(value["value"])
    if kind == "real":
        return float(value["value"])
    return value["value"]

after = {"tables": {}}
with sqlite3.connect(f"file:{database}?mode=ro", uri=True) as connection:
    for table in ("clients", "devices", "device_credentials"):
        expected = before["tables"][table]
        columns = [row[1] for row in connection.execute(f"PRAGMA table_info({table})")]
        if columns != expected["columns"]:
            raise SystemExit(f"{table} schema changed during Update")
        select = ", ".join(f'"{column}"' for column in columns)
        rows = connection.execute(f'SELECT {select} FROM "{table}" ORDER BY {select}').fetchall()
        after["tables"][table] = {
            "columns": columns,
            "rows": [[encode(value) for value in row] for row in rows],
        }

for table in ("clients", "devices"):
    if after["tables"][table] != before["tables"][table]:
        raise SystemExit(f"{table} changed during Update")

before_credentials = before["tables"]["device_credentials"]
after_credentials = after["tables"]["device_credentials"]
columns = before_credentials["columns"]
try:
    device_index = columns.index("device_id")
    engine_index = columns.index("engine")
    status_index = columns.index("status")
    config_index = columns.index("config_json")
except ValueError as exc:
    raise SystemExit("device_credentials lacks device_id/engine/status/config_json") from exc

before_rows = before_credentials["rows"]
after_rows = after_credentials["rows"]

def rows_by_pair(rows, label):
    result = {}
    for row in rows:
        pair = (decode(row[device_index]), decode(row[engine_index]))
        if pair in result:
            raise SystemExit(f"duplicate device credential records detected in {label}")
        result[pair] = row
    return result

before_by_pair = rows_by_pair(before_rows, "pre-update state")
after_by_pair = rows_by_pair(after_rows, "post-update state")
allowed_awg31_config_changes = {
    "profile", "engine", "client_name", "dns", "endpoint", "transport",
    "interface", "network", "allowed_ips", "persistent_keepalive",
    "generation", "server_public_key",
    "i1", "i2", "i3", "i4", "i5",
    "jc", "jmin", "jmax", "s1", "s2", "s3", "s4",
    "h1", "h2", "h3", "h4",
}
updated_awg31 = 0
missing = object()

for pair, before_row in before_by_pair.items():
    after_row = after_by_pair.get(pair)
    if after_row is None:
        raise SystemExit("an existing credential was removed during Update")
    if after_row == before_row:
        continue

    device_id, engine = pair
    if engine != "amneziawg31":
        raise SystemExit("an existing non-AWG31 credential changed during Update")

    for index, column in enumerate(columns):
        if column in {"status", "config_json"}:
            continue
        if after_row[index] != before_row[index]:
            raise SystemExit(
                f"protected AWG31 credential field changed during Update: {column}"
            )

    try:
        before_config = json.loads(decode(before_row[config_index]) or "{}")
        after_config = json.loads(decode(after_row[config_index]) or "{}")
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise SystemExit("existing AWG31 credential config_json is invalid") from exc
    if not isinstance(before_config, dict) or not isinstance(after_config, dict):
        raise SystemExit("existing AWG31 credential config_json must be an object")

    for key in set(before_config) | set(after_config):
        if key.lower() in allowed_awg31_config_changes:
            continue
        if before_config.get(key, missing) != after_config.get(key, missing):
            raise SystemExit(
                f"protected AWG31 credential config field changed during Update: {key}"
            )

    before_status = decode(before_row[status_index])
    after_status = decode(after_row[status_index])
    if before_status != after_status and after_status != "pending":
        raise SystemExit("existing AWG31 credential received an unsafe status transition")
    updated_awg31 += 1

added = [
    after_by_pair[pair]
    for pair in after_by_pair.keys() - before_by_pair.keys()
]

device_table = before["tables"]["devices"]
device_columns = device_table["columns"]
device_id_index = device_columns.index("id")
device_ids = {decode(row[device_id_index]) for row in device_table["rows"]}
before_pairs = set(before_by_pair)
for row in added:
    device_id = decode(row[device_index])
    engine = decode(row[engine_index])
    if engine != "amneziawg31" or device_id not in device_ids:
        raise SystemExit("Update added a credential outside the AWG31 migration allowance")
    if (device_id, engine) in before_pairs:
        raise SystemExit("Update duplicated an existing AWG31 credential")

awg31_devices = {
    device_id for device_id, engine in after_by_pair if engine == "amneziawg31"
}
if awg31_devices != device_ids:
    raise SystemExit("AWG31 migration did not create exactly one credential for every existing device")

print(
    f"Credentials transition: preserved={len(before_rows)} "
    f"added_awg31={len(added)} updated_awg31={updated_awg31}"
)
PYCREDENTIALVERIFY
}

capture_service_states() {
  local output="$1" service active enabled failed
  : > "$output"
  for service in \
    nginx.service xray.service mihomo.service sg-gateway-awg.service "$AWG3_SERVICE" "$AWG31_SERVICE" \
    sg-gateway-singbox.service "$HOSTD_SERVICE" "$PANEL_SERVICE"; do
    active=0
    enabled=0
    failed=0
    systemctl is-active --quiet "$service" && active=1 || true
    systemctl is-enabled --quiet "$service" && enabled=1 || true
    systemctl is-failed --quiet "$service" && failed=1 || true
    printf '%s\t%s\t%s\t%s\n' "$service" "$active" "$enabled" "$failed" >> "$output"
  done
}

verify_runtime_states_unchanged() {
  local before="$1" service active enabled failed now now_enabled now_failed
  while IFS=$'\t' read -r service active enabled failed; do
    [[ -n "$service" ]] || continue
    case "$service" in
      "$PANEL_SERVICE"|"$HOSTD_SERVICE"|"$AWG31_SERVICE") continue ;;
    esac
    now=0
    now_enabled=0
    now_failed=0
    systemctl is-active --quiet "$service" && now=1 || true
    systemctl is-enabled --quiet "$service" && now_enabled=1 || true
    systemctl is-failed --quiet "$service" && now_failed=1 || true
    if [[ "$now" != "$active" || "$now_enabled" != "$enabled" || "$now_failed" != "$failed" ]]; then
      echo "Runtime service state changed: $service active $active->$now enabled $enabled->$now_enabled failed $failed->$now_failed" >&2
      return 1
    fi
  done < "$before"
}

https_state() {
  local state_file="$DATA_DIR/security/tls-state.json"
  local runtime_file="$CONFIG_DIR/runtime.env"
  local panel_port
  panel_port="$(env_value "$runtime_file" SG_GATEWAY_PANEL_PORT 2>/dev/null || true)"
  python3 - "$state_file" "$panel_port" <<'PYHTTPS'
import json
import shlex
import sys
from pathlib import Path

state_path = Path(sys.argv[1])
panel_port = str(sys.argv[2] or "").strip()
payload = {}
try:
    payload = json.loads(state_path.read_text(encoding="utf-8"))
except Exception:
    payload = {}

ready = bool(payload.get("https_ready"))
domain = str(payload.get("domain") or "").strip().lower().rstrip(".")
cert = str(payload.get("certificate_path") or "").strip()
key = str(payload.get("key_path") or "").strip()
public_port = str(payload.get("public_port") or payload.get("panel_port") or panel_port or "").strip()

if ready:
    if not domain or not cert or not key or not Path(cert).is_file() or not Path(key).is_file():
        raise SystemExit("HTTPS state says ready, but domain/certificate/key is incomplete")
    if panel_port and public_port and panel_port != public_port:
        raise SystemExit(f"HTTPS port mismatch: state={public_port} runtime={panel_port}")

for name, value in (
    ("HTTPS_READY", "1" if ready else "0"),
    ("HTTPS_DOMAIN", domain),
    ("HTTPS_CERT", cert),
    ("HTTPS_KEY", key),
    ("PANEL_PORT", public_port or panel_port),
):
    print(f"{name}={shlex.quote(value)}")
PYHTTPS
}

protected_runtime_paths() {
  local https_env="$1" output="$2"
  local cert="" key=""
  # shellcheck disable=SC1090
  source "$https_env"
  cert="${HTTPS_CERT:-}"
  key="${HTTPS_KEY:-}"
  python3 - "$output" \
    "$LETSENCRYPT_DIR" "$DATA_DIR/security/tls-state.json" \
    "$AWG2_CONFIG" "$AWG2_UNIT" \
    "$AWG3_CONFIG" "$AWG3_UNIT" "$AWG3_ROOT" \
    "$AWG31_CONFIG" "$AWG31_STATE" "$AWG31_UNIT" "$PREFIX/awg31" \
    -- "$cert" "$key" <<'PYPROTECTED'
import os
import sys
from pathlib import Path

output = Path(sys.argv[1])
separator = sys.argv.index("--")
values = list(sys.argv[2:separator])
for raw in sys.argv[separator + 1:]:
    raw = str(raw or "").strip()
    if not raw:
        continue
    path = Path(raw)
    if not path.is_absolute() or ".." in path.parts or str(path) == "/":
        raise SystemExit(f"unsafe protected runtime path: {raw!r}")
    values.append(os.path.normpath(str(path)))
    if path.exists() or path.is_symlink():
        values.append(os.path.realpath(str(path)))

seen = set()
ordered = []
for raw in values:
    value = os.path.normpath(str(raw))
    if value == "/" or not value.startswith("/") or value in seen:
        continue
    seen.add(value)
    ordered.append(value)
output.write_text("\n".join(ordered) + "\n", encoding="utf-8")
PYPROTECTED
}

relative_to_system_root() {
  local path="$1"
  if [[ "$SYSTEM_ROOT" == / ]]; then
    [[ "$path" == /* ]] || return 1
    printf '%s\n' "${path#/}"
    return 0
  fi
  case "$path" in
    "$SYSTEM_ROOT"/*) printf '%s\n' "${path#"$SYSTEM_ROOT"/}" ;;
    *) return 1 ;;
  esac
}

preserved_runtime_paths() {
  local source="$1" output="$2" path
  : > "$output"
  while IFS= read -r path; do
    [[ -n "$path" ]] || continue
    case "$path" in
      "$AWG31_CONFIG"|"$AWG31_CONFIG"/*|"$AWG31_STATE"|"$AWG31_STATE"/*|"$AWG31_UNIT"|"$PREFIX/awg31"|"$PREFIX/awg31"/*)
        continue
        ;;
    esac
    printf '%s\n' "$path" >> "$output"
  done < "$source"
}

create_safety_backup() {
  mkdir -p "$BACKUP_ROOT"
  chmod 0700 "$BACKUP_ROOT"

  cleanup_incomplete_safety_backups
  local pre_keep=1
  if (( BACKUP_KEEP > 1 )); then
    pre_keep=$(( BACKUP_KEEP - 1 ))
  fi
  prune_safety_backups "$pre_keep"

  BACKUP_DIR="$BACKUP_ROOT/$(date -u +%Y%m%d-%H%M%S)-before-update"
  mkdir -p "$BACKUP_DIR"
  chmod 0700 "$BACKUP_DIR"

  # Refuse the update before stopping services when the rollback archive
  # cannot fit on disk. The reserve also covers tar metadata and update work.
  ensure_safety_backup_space

  capture_service_states "$BACKUP_DIR/service-state.tsv"
  systemctl stop "$PANEL_SERVICE" "$HOSTD_SERVICE"
  SERVICES_STOPPED=1

  https_state > "$BACKUP_DIR/https-before.env"
  protected_runtime_paths "$BACKUP_DIR/https-before.env" "$BACKUP_DIR/protected-runtime-paths.txt"
  preserved_runtime_paths "$BACKUP_DIR/protected-runtime-paths.txt" "$BACKUP_DIR/preserved-runtime-paths.txt"

  local protected_paths=()
  mapfile -t protected_paths < "$BACKUP_DIR/preserved-runtime-paths.txt"
  fingerprint_paths "${protected_paths[@]}" > "$BACKUP_DIR/protected-runtime-before.sha256"
  fingerprint_clients > "$BACKUP_DIR/clients-before.sha256"
  capture_credentials_state "$BACKUP_DIR/credentials-before.json"
  fingerprint_paths "$LETSENCRYPT_DIR" > "$BACKUP_DIR/letsencrypt-before.sha256"
  fingerprint_paths \
    "$NGINX_CONFIG" \
    "$NGINX_SITE_AVAILABLE" \
    "$NGINX_SITE_ENABLED" \
    "$NGINX_STREAM_CONFIG" \
    > "$BACKUP_DIR/nginx-before.sha256"

  local existing=() relative absolute
  for relative in \
    opt/sg-gateway \
    etc/sg-gateway \
    var/lib/sg-gateway \
    etc/letsencrypt \
    etc/amnezia/amneziawg/awg0.conf \
    etc/amnezia/amneziawg/awg3.conf \
    etc/amnezia/amneziawg/awg31 \
    etc/nginx/nginx.conf \
    etc/nginx/sites-available/sg-gateway \
    etc/nginx/sites-enabled/sg-gateway \
    etc/nginx/stream-conf.d/sg-gateway-443.conf \
    etc/systemd/system/sg-gateway.service \
    etc/systemd/system/sg-hostd.service \
    etc/systemd/system/sg-gateway-awg.service \
    etc/systemd/system/sg-gateway-awg3.service \
    etc/systemd/system/sg-gateway-awg31.service; do
    if [[ -e "$SYSTEM_ROOT/$relative" || -L "$SYSTEM_ROOT/$relative" ]]; then
      existing+=("$relative")
    fi
  done

  while IFS= read -r absolute; do
    [[ -n "$absolute" && "$absolute" == /* ]] || continue
    if [[ -e "$absolute" || -L "$absolute" ]]; then
      relative="$(relative_to_system_root "$absolute")" || \
        fail "protected runtime path is outside SG_GATEWAY_ROOT: $absolute"
      existing+=("$relative")
    fi
  done < "$BACKUP_DIR/protected-runtime-paths.txt"

  local unique=() filtered=() item kept_path covered
  for item in "${existing[@]}"; do
    item="${item#/}"
    item="${item%/}"
    [[ -n "$item" ]] || continue
    covered=0
    for kept_path in "${unique[@]}"; do
      if [[ "$item" == "$kept_path" || "$item" == "$kept_path/"* ]]; then
        covered=1
        break
      fi
    done
    (( covered == 1 )) && continue
    filtered=()
    for kept_path in "${unique[@]}"; do
      [[ "$kept_path" == "$item/"* ]] && continue
      filtered+=("$kept_path")
    done
    unique=("${filtered[@]}" "$item")
  done
  existing=("${unique[@]}")

  printf '%s\n' "${existing[@]}" > "$BACKUP_DIR/existing-paths.txt"
  tar -C "$SYSTEM_ROOT" -cpf "$BACKUP_DIR/state.tar" "${existing[@]}"
  tar -tf "$BACKUP_DIR/state.tar" >/dev/null
  BACKUP_READY=1
}

rollback_update() {
  (( BACKUP_READY == 1 )) || return 0
  printf '\n%s[SG-Gateway Update] ROLLBACK:%s restoring the pre-update server state...\n' "$YELLOW" "$RESET"
  systemctl stop "$PANEL_SERVICE" "$HOSTD_SERVICE" "$AWG3_SERVICE" "$AWG31_SERVICE" >/dev/null 2>&1 || true

  local path
  for path in \
    "$PREFIX" \
    "$CONFIG_DIR" \
    "$DATA_DIR" \
    "$LETSENCRYPT_DIR" \
    "$AWG2_CONFIG" \
    "$AWG3_CONFIG" \
    "$AWG31_CONFIG" \
    "$NGINX_SITE_AVAILABLE" \
    "$NGINX_SITE_ENABLED" \
    "$NGINX_STREAM_CONFIG" \
    "$PANEL_UNIT" \
    "$HOSTD_UNIT" \
    "$AWG2_UNIT" \
    "$AWG3_UNIT" \
    "$AWG31_UNIT"; do
    rm -rf -- "$path"
  done

  while IFS= read -r path; do
    [[ -n "$path" && "$path" == /* ]] || continue
    relative_to_system_root "$path" >/dev/null || continue
    [[ "$path" != "$SYSTEM_ROOT" && "$path" != / ]] || continue
    rm -rf -- "$path"
  done < "$BACKUP_DIR/protected-runtime-paths.txt"

  tar -C "$SYSTEM_ROOT" -xpf "$BACKUP_DIR/state.tar"
  systemctl daemon-reload >/dev/null 2>&1 || true

  if command -v nginx >/dev/null 2>&1 && nginx -t >/dev/null 2>&1; then
    systemctl is-active --quiet nginx.service && systemctl reload nginx.service >/dev/null 2>&1 || true
  fi

  local service active enabled failed
  while IFS=$'\t' read -r service active enabled failed; do
    [[ -n "$service" ]] || continue
    if [[ "$enabled" == "1" ]]; then
      systemctl enable "$service" >/dev/null 2>&1 || true
    else
      systemctl disable "$service" >/dev/null 2>&1 || true
    fi
    if [[ "$active" == "1" ]]; then
      systemctl restart "$service" >/dev/null 2>&1 || true
    else
      systemctl stop "$service" >/dev/null 2>&1 || true
    fi
  done < "$BACKUP_DIR/service-state.tsv"

  printf '%s[SG-Gateway Update] ROLLBACK OK.%s Backup: %s\n' "$GREEN" "$RESET" "$BACKUP_DIR"
}

on_error() {
  local rc=$?
  trap - ERR INT TERM
  if (( UPDATE_FINISHED == 0 )); then
    if (( BACKUP_READY == 1 )); then
      rollback_update || true
    elif (( SERVICES_STOPPED == 1 )); then
      systemctl start "$HOSTD_SERVICE" >/dev/null 2>&1 || true
      systemctl start "$PANEL_SERVICE" >/dev/null 2>&1 || true
    fi
  fi
  if (( BACKUP_READY == 0 )); then
    remove_current_incomplete_backup || true
  fi
  cleanup
  printf '%s[SG-Gateway Update] Update failed.%s\n' "$RED" "$RESET" >&2
  exit "$rc"
}
run_stage() {
  local number="$1" label="$2"
  shift 2
  printf '%s[SG-Gateway Update] [%s/7]%s %s\n' "$CYAN" "$number" "$RESET" "$label"
  "$@"
  printf '%s[SG-Gateway Update] [OK]%s %s\n' "$GREEN" "$RESET" "$label"
}

# SG_GATEWAY_02205_WSGI_ISOLATED_VALIDATION_V1
installed_panel_wsgi_target() {
  local raw
  raw="$(systemctl show -p ExecStart --value "$PANEL_SERVICE" 2>/dev/null || true)"
  python3 - "$raw" <<'PYWSGITARGET'
import re
import sys

raw = sys.argv[1]
items = re.findall(
    r"(?<![A-Za-z0-9_.])([A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*:[A-Za-z_]\w*)(?![A-Za-z0-9_])",
    raw,
)
print(items[-1] if items else "")
PYWSGITARGET
}

panel_wsgi_target() {
  printf '%s\n' "$PANEL_PRODUCTION_WSGI"
}

# SG_GATEWAY_02204E_UPDATE_PRODUCTION_WSGI_FIX1
migrate_panel_wsgi_service() {
  local unit="$PANEL_UNIT"
  local current after
  [[ -f "$unit" ]] || fail "panel systemd unit is missing: $unit"

  current="$(installed_panel_wsgi_target)"
  if [[ "$current" == "$PANEL_PRODUCTION_WSGI" ]]; then
    printf '[SG-Gateway Update] Panel WSGI target: %s (already current).\n' "$current"
    return 0
  fi
  [[ -n "$current" ]] || fail "cannot determine installed panel WSGI target"

  python3 - "$unit" "$PANEL_PRODUCTION_WSGI" <<'PYMIGRATEWSGI'
import re
import sys
from pathlib import Path

path = Path(sys.argv[1])
target = sys.argv[2]
body = path.read_text(encoding="utf-8")
lines = body.splitlines(keepends=True)
pattern = re.compile(
    r"(?<![A-Za-z0-9_.])([A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*:[A-Za-z_]\w*)(?![A-Za-z0-9_])"
)
hits = []
for index, line in enumerate(lines):
    if not line.startswith("ExecStart="):
        continue
    matches = list(pattern.finditer(line))
    if len(matches) == 1:
        hits.append((index, matches[0]))
if len(hits) != 1:
    raise SystemExit(f"expected exactly one WSGI target in ExecStart, found {len(hits)}")
index, match = hits[0]
line = lines[index]
lines[index] = line[:match.start()] + target + line[match.end():]
path.write_text("".join(lines), encoding="utf-8", newline="")
PYMIGRATEWSGI

  systemctl daemon-reload
  after="$(installed_panel_wsgi_target)"
  [[ "$after" == "$PANEL_PRODUCTION_WSGI" ]] || \
    fail "panel WSGI migration failed: expected $PANEL_PRODUCTION_WSGI, got ${after:-unknown}"
  printf '[SG-Gateway Update] Panel WSGI migrated: %s -> %s\n' "$current" "$after"
}

validate_candidate_wsgi_target() {
  local source="$1" target module
  target="$(panel_wsgi_target)"
  module="${target%%:*}"
  "$PREFIX/.venv/bin/python" -B - "$source" "$module" "$target" <<'PYCANDIDATEWSGI'
import sys
from pathlib import Path

root = Path(sys.argv[1])
module = sys.argv[2]
target = sys.argv[3]
module_path = root.joinpath(*module.split("."))
present = module_path.with_suffix(".py").is_file() or (module_path / "__init__.py").is_file()
if not present:
    raise SystemExit(
        f"candidate source does not provide installed panel WSGI target {target}"
    )
print(f"Candidate WSGI target: {target} -> module present")
PYCANDIDATEWSGI
}

validate_deployed_panel() {
  runuser -u sg-gateway -- "$PREFIX/.venv/bin/python" -B -c \
    'import sys; from pathlib import Path; from jinja2 import Environment; env=Environment(); [env.parse(p.read_text(encoding="utf-8")) for p in Path(sys.argv[1]).rglob("*.html")]; print("Templates: OK")' \
    "$PREFIX/app/web/templates"

  local target validation_root validation_env
  target="$(panel_wsgi_target)"
  validation_root="$TEMP_DIR/wsgi-validation"
  rm -rf "$validation_root"
  # TEMP_DIR is created root:root 0700 by mktemp. The deployed WSGI import
  # runs as sg-gateway, so allow traversal only for the duration of this
  # isolated validation. Directory listing remains denied.
  chmod 0711 "$TEMP_DIR"
  if [[ "$SYSTEM_ROOT" == / ]]; then
    install -d -m 0750 -o sg-gateway -g sg-gateway \
      "$validation_root" "$validation_root/data" "$validation_root/log"
  else
    install -d -m 0750 "$validation_root" "$validation_root/data" "$validation_root/log"
  fi
  validation_env="$validation_root/sg-gateway.env"
  if [[ "$SYSTEM_ROOT" == / ]]; then
    install -m 0600 -o sg-gateway -g sg-gateway "$CONFIG_DIR/sg-gateway.env" "$validation_env"
  else
    install -m 0600 "$CONFIG_DIR/sg-gateway.env" "$validation_env"
  fi

  runuser -u sg-gateway -- "$PREFIX/.venv/bin/python" -B - \
    "$PREFIX" "$validation_env" "$target" "$validation_root" <<'PYDEPLOYEDWSGI'
import importlib
import os
import shlex
import sys
from pathlib import Path

prefix = Path(sys.argv[1])
env_file = Path(sys.argv[2])
target = sys.argv[3]
validation_root = Path(sys.argv[4])

for raw in env_file.read_text(encoding="utf-8").splitlines():
    line = raw.strip()
    if not line or line.startswith("#") or "=" not in line:
        continue
    name, value = line.split("=", 1)
    name = name.strip()
    value = value.strip()
    if value[:1] in {'"', "'"}:
        try:
            parsed = shlex.split(value, posix=True)
            value = parsed[0] if parsed else ""
        except ValueError:
            value = value[1:-1] if len(value) >= 2 else ""
    os.environ[name] = value

# The import can execute app.main -> init_db(). Keep it away from production.
os.environ["SG_GATEWAY_DATA_DIR"] = str(validation_root / "data")
os.environ["SG_GATEWAY_LOG_DIR"] = str(validation_root / "log")

os.chdir(prefix)
sys.path.insert(0, str(prefix))
module_name, object_name = target.split(":", 1)
module = importlib.import_module(module_name)
application = getattr(module, object_name)
if target == "app.production:app":
    with application.test_request_context("/"):
        context = {}
        for processor in application.template_context_processors[None]:
            context.update(processor())
    required = (
        "sg_subscription_universal_url",
        "sg_subscription_native_url",
        "router_subscription_url",
        "openwrt_subscription_url",
        "keenetic_subscription_url",
    )
    missing = [name for name in required if not callable(context.get(name))]
    if missing:
        raise SystemExit(
            "production WSGI is missing required template context: " + ", ".join(missing)
        )
    print("Production template context: OK")
print(f"Panel WSGI import: OK ({target}) with isolated data/log")
PYDEPLOYEDWSGI
  chmod 0700 "$TEMP_DIR"
}

preflight() {
  [[ "$(id -u)" -eq 0 ]] || fail "run this updater through sudo"
  [[ -f "$PREFIX/VERSION" && -f "$CONFIG_DIR/runtime.env" && -f "$CONFIG_DIR/sg-gateway.env" ]] || {
    fail "SG-Gateway is not installed. Use the Clean Install command instead."
  }

  validate_backup_policy

  local command
  for command in curl tar gzip python3 sha256sum systemctl du df find sort; do
    command -v "$command" >/dev/null 2>&1 || fail "required command is missing: $command"
  done

  systemctl is-active --quiet nginx.service || fail "nginx.service is not active before update"
  systemctl is-active --quiet "$HOSTD_SERVICE" || fail "$HOSTD_SERVICE is not active before update"
  systemctl is-active --quiet "$PANEL_SERVICE" || fail "$PANEL_SERVICE is not active before update"

  local old_version
  old_version="$(tr -d '\r\n' < "$PREFIX/VERSION")"
  printf '[SG-Gateway Update] Installed VERSION: %s\n' "$old_version"

  local state
  state="$(https_state)"
  eval "$state"
  if [[ "${HTTPS_READY:-0}" == "1" ]]; then
    printf '[SG-Gateway Update] HTTPS: %s:%s\n' "$HTTPS_DOMAIN" "$PANEL_PORT"
    curl --noproxy '*' -fsS --max-time 12 \
      --resolve "${HTTPS_DOMAIN}:${PANEL_PORT}:127.0.0.1" \
      "https://${HTTPS_DOMAIN}:${PANEL_PORT}/health" >/dev/null
  else
    printf '[SG-Gateway Update] HTTPS: not configured; IP/HTTP mode will be preserved.\n'
  fi
}

resolve_source_commit() {
  local resolved="$SOURCE_COMMIT" encoded

  if [[ "$resolved" =~ ^[0-9a-fA-F]{40}$ ]]; then
    SOURCE_COMMIT="${resolved,,}"
    return 0
  fi

  if command -v git >/dev/null 2>&1; then
    resolved="$(git ls-remote --exit-code "$GIT_URL" "refs/heads/$BRANCH" 2>/dev/null | awk 'NR==1 {print $1}' || true)"
  fi

  if [[ ! "$resolved" =~ ^[0-9a-f]{40}$ ]]; then
    encoded="$(python3 -c 'import sys,urllib.parse; print(urllib.parse.quote(sys.argv[1], safe=""))' "$BRANCH")"
    resolved="$(
      curl -4 -fsSL --max-time 20 -A 'SG-Gateway-Updater' \
        "https://api.github.com/repos/${REPOSITORY}/commits/${encoded}" 2>/dev/null \
      | python3 -c 'import json,re,sys; value=str(json.load(sys.stdin).get("sha") or "").strip().lower(); print(value if re.fullmatch(r"[0-9a-f]{40}", value) else "")' \
        2>/dev/null || true
    )"
  fi

  if [[ ! "$resolved" =~ ^[0-9a-f]{40}$ ]]; then
    resolved="$(
      curl -4 -fsSL --max-time 20 -A 'SG-Gateway-Updater' \
        "https://github.com/${REPOSITORY}/commits/${encoded}.atom" 2>/dev/null \
      | python3 -c 'import re,sys; match=re.search(r"Grit::Commit/([0-9a-fA-F]{40})", sys.stdin.read()); print(match.group(1).lower() if match else "")' \
        2>/dev/null || true
    )"
  fi

  [[ "$resolved" =~ ^[0-9a-fA-F]{40}$ ]] || fail "cannot resolve exact GitHub commit for update channel $BRANCH"
  SOURCE_COMMIT="${resolved,,}"
}

prepare_source_archive() {
  local archive archive_url
  resolve_source_commit
  archive="$TEMP_DIR/sg-gateway-${SOURCE_COMMIT}.tar.gz"
  archive_url="https://github.com/${REPOSITORY}/archive/${SOURCE_COMMIT}.tar.gz"
  rm -rf "$SOURCE_DIR"
  mkdir -p "$SOURCE_DIR"

  printf '[SG-Gateway Update] Source mode: COMPATIBILITY (full GitHub archive)\n'
  printf '[SG-Gateway Update] Source commit: %s\n' "$SOURCE_COMMIT"
  curl -fL --retry 6 --retry-all-errors --retry-delay 3 --connect-timeout 20 \
    "$archive_url" -o "$archive"
  gzip -t "$archive"
  tar -xzf "$archive" -C "$SOURCE_DIR" --strip-components=1
}

validate_runtime_sources() {
  local directory="$1" index filename expected actual
  for index in "${!RUNTIME_FILES[@]}"; do
    filename="${RUNTIME_FILES[$index]}"
    expected="${RUNTIME_SHA256[$index]}"
    [[ -f "$directory/$filename" ]] || fail "required Stage3A runtime is missing: $filename"
    actual="$(sha256sum "$directory/$filename" | awk '{print $1}')"
    [[ "$actual" == "$expected" ]] || \
      fail "Stage3A runtime SHA-256 mismatch: $filename (expected $expected, got $actual)"
  done
}

stage_runtime_sources() {
  local source="$1" stage="$2" filename
  rm -rf -- "$stage"
  mkdir -p "$stage/vendor/cores"
  [[ -d "$source/deploy" ]] || fail "deploy source is missing from Stage3A source"
  cp -a "$source/deploy" "$stage/deploy"
  for filename in "${RUNTIME_FILES[@]}"; do
    [[ -f "$source/vendor/cores/$filename" ]] || \
      fail "required Stage3A runtime is missing: $filename"
    cp -a "$source/vendor/cores/$filename" "$stage/vendor/cores/$filename"
  done
  validate_runtime_sources "$stage/vendor/cores"
  local count
  count="$(find "$stage/vendor/cores" -mindepth 1 -maxdepth 1 -type f | wc -l)"
  [[ "$count" == "${#RUNTIME_FILES[@]}" ]] || fail "Stage3A runtime staging contains unexpected files"
  printf '[SG-Gateway Update] Stage3A runtime staging: %s verified files\n' "$count"
}

prepare_source_light() {
  command -v git >/dev/null 2>&1 || return 1

  resolve_source_commit

  rm -rf "$SOURCE_DIR"
  printf '[SG-Gateway Update] Source mode: LIGHT\n'
  printf '[SG-Gateway Update] Git partial clone: depth=1 + blob:none + runtime whitelist\n'
  printf '[SG-Gateway Update] non-runtime trees: assets/data/docs/tests/.github and non-whitelisted vendor skipped\n'

  git -c advice.detachedHead=false clone \
    --quiet \
    --depth=1 \
    --filter=blob:none \
    --no-checkout \
    --single-branch \
    --branch "$BRANCH" \
    "$GIT_URL" "$SOURCE_DIR" || return 1

  git -C "$SOURCE_DIR" sparse-checkout init --no-cone || return 1
  git -C "$SOURCE_DIR" sparse-checkout set --no-cone \
    /VERSION \
    /requirements.txt \
    /app/ \
    /hostd/requirements.txt \
    /hostd/sg_hostd/ \
    /deploy/ \
    /vendor/cores/amneziawg-tools-3.0.20260805.tar.gz \
    /vendor/cores/amneziawg-go-linux-amd64-v3.0.0 \
    /vendor/cores/amneziawg-tools-3.1.20260812.tar.gz \
    /vendor/cores/amneziawg-go-linux-amd64-v3.1.20260814 || return 1
  git -C "$SOURCE_DIR" checkout --quiet --detach "$SOURCE_COMMIT" || return 1
  [[ "$(git -C "$SOURCE_DIR" rev-parse HEAD 2>/dev/null || true)" == "$SOURCE_COMMIT" ]] || return 1
  printf '[SG-Gateway Update] Source commit: %s\n' "$SOURCE_COMMIT"

  local forbidden
  for forbidden in assets data docs tests .github; do
    [[ ! -e "$SOURCE_DIR/$forbidden" ]] || {
      echo "[SG-Gateway Update] LIGHT source unexpectedly contains: $forbidden" >&2
      return 1
    }
  done
  validate_runtime_sources "$SOURCE_DIR/vendor/cores" || return 1
  local runtime_count
  runtime_count="$(find "$SOURCE_DIR/vendor/cores" -mindepth 1 -maxdepth 1 -type f | wc -l)"
  [[ "$runtime_count" == "${#RUNTIME_FILES[@]}" ]] || return 1

  local object_size source_size
  object_size="$(du -sh "$SOURCE_DIR/.git/objects" 2>/dev/null | awk '{print $1}' || true)"
  source_size="$(du -sh --exclude=.git "$SOURCE_DIR" 2>/dev/null | awk '{print $1}' || true)"
  [[ -n "$object_size" ]] && printf '[SG-Gateway Update] Git objects fetched: %s\n' "$object_size"
  [[ -n "$source_size" ]] && printf '[SG-Gateway Update] Checked-out source: %s\n' "$source_size"

  rm -rf "$SOURCE_DIR/.git"
}

prepare_source() {
  TEMP_DIR="$(mktemp -d /tmp/sg-gateway-github-update.XXXXXX)"
  SOURCE_DIR="$TEMP_DIR/source"

  # SG_GATEWAY_02112_LIGHT_UPDATE_FIX9
  if command -v git >/dev/null 2>&1; then
    if ! prepare_source_light; then
      printf '[SG-Gateway Update] LIGHT source failed; falling back to full archive.\n' >&2
      prepare_source_archive
    fi
  else
    printf '[SG-Gateway Update] git is not installed; using compatibility source mode.\n'
    prepare_source_archive
  fi

  [[ -f "$SOURCE_DIR/VERSION" ]] || fail "VERSION is missing from GitHub source"
  [[ -f "$SOURCE_DIR/requirements.txt" ]] || fail "requirements.txt is missing from GitHub source"
  [[ -f "$SOURCE_DIR/hostd/requirements.txt" ]] || fail "hostd/requirements.txt is missing from GitHub source"
  [[ -f "$SOURCE_DIR/app/main.py" ]] || fail "app/main.py is missing from GitHub source"
  [[ -f "$SOURCE_DIR/app/production.py" ]] || fail "app/production.py is missing from GitHub source"
  [[ -f "$SOURCE_DIR/hostd/sg_hostd/app.py" ]] || fail "hostd source is missing from GitHub source"

  if ! cmp -s "$PREFIX/requirements.txt" "$SOURCE_DIR/requirements.txt"; then
    fail "requirements.txt changed. Safe panel-only Update is blocked; a dedicated dependency migration is required."
  fi
  if [[ -f "$PREFIX/hostd/requirements.txt" ]] && ! cmp -s "$PREFIX/hostd/requirements.txt" "$SOURCE_DIR/hostd/requirements.txt"; then
    fail "hostd/requirements.txt changed. Safe panel-only Update is blocked; a dedicated dependency migration is required."
  fi

  # SG_GATEWAY_02112_UPDATE_SOURCE_DIR_FIX8
  "$PREFIX/.venv/bin/python" -B - "$SOURCE_DIR" <<'PYCHECK'
import compileall
import sys
from pathlib import Path
root = Path(sys.argv[1])
ok = compileall.compile_dir(root / "app", quiet=1)
ok = compileall.compile_dir(root / "hostd" / "sg_hostd", quiet=1) and ok
if not ok:
    raise SystemExit("Python syntax validation failed")
print("Python syntax: OK")
PYCHECK

  validate_candidate_wsgi_target "$SOURCE_DIR"

  MIGRATION_SOURCE_DIR="$TEMP_DIR/stage3a-source"
  stage_runtime_sources "$SOURCE_DIR" "$MIGRATION_SOURCE_DIR"
}

# SG_GATEWAY_02112_LIGHT_UPDATE_ASSET_PRESERVE_FIX10
prepare_preserved_assets() {
  local live="$PREFIX/assets"
  local country_rel="geoip/sg-country-geoip.dat"
  local archive listing archives recover_root

  ASSETS_FINGERPRINT=""
  ASSETS_RECOVERY_DIR=""
  ASSETS_RECOVERY_SOURCE=""

  if [[ -f "$live/$country_rel" ]]; then
    ASSETS_FINGERPRINT="$(fingerprint_tree_relative "$live")"
    ASSETS_RECOVERY_SOURCE="live"
    printf '[SG-Gateway Update] Local assets: preserving installed payload (not downloaded).\n'
    return 0
  fi

  # FIX9-R2 could remove /opt/sg-gateway/assets on an already-updated
  # server. Recover the last complete copy from our own pre-update
  # Safety Backups. Never re-download the 100+ MB asset tree in Light mode.
  listing="$TEMP_DIR/assets-backup-list.txt"
  archives="$TEMP_DIR/assets-backup-archives.txt"
  find "$BACKUP_ROOT" -mindepth 2 -maxdepth 2 -type f -name state.tar -print 2>/dev/null | sort -r > "$archives"
  while IFS= read -r archive; do
    [[ -f "$archive" ]] || continue
    : > "$listing"
    tar -tf "$archive" > "$listing" 2>/dev/null || continue
    grep -Fxq "opt/sg-gateway/assets/$country_rel" "$listing" || continue

    recover_root="$TEMP_DIR/recovered-assets"
    rm -rf "$recover_root"
    mkdir -p "$recover_root"
    tar -C "$recover_root" -xpf "$archive" opt/sg-gateway/assets || continue
    [[ -f "$recover_root/opt/sg-gateway/assets/$country_rel" ]] || continue

    ASSETS_RECOVERY_DIR="$recover_root/opt/sg-gateway/assets"
    ASSETS_FINGERPRINT="$(fingerprint_tree_relative "$ASSETS_RECOVERY_DIR")"
    ASSETS_RECOVERY_SOURCE="$(basename "$(dirname "$archive")")"
    printf '[SG-Gateway Update] Local assets: recovered from Safety Backup %s.\n' "$ASSETS_RECOVERY_SOURCE"
    return 0
  done < "$archives"

  fail "local assets are missing and no Safety Backup with assets was found; refusing to change the installed application"
}

deploy_source() {
  local source="$1"
  local stage="$TEMP_DIR/live-source"
  rm -rf "$stage"
  mkdir -p "$stage"
  cp -a "$source/." "$stage/"
  rm -rf "$stage/vendor/cores" "$stage/.git" "$stage/.github"
  rm -f "$stage/install.sh"

  prepare_preserved_assets

  if (( SERVICES_STOPPED == 0 )); then
    systemctl stop "$PANEL_SERVICE" "$HOSTD_SERVICE"
    SERVICES_STOPPED=1
  fi

  local child children
  children="$TEMP_DIR/prefix-children.bin"
  find "$PREFIX" -mindepth 1 -maxdepth 1 -print0 > "$children"
  while IFS= read -r -d '' child; do
    case "$(basename "$child")" in
      ".venv"|"awg3") continue ;;
      "assets") continue ;;
    esac
    rm -rf "$child"
  done < "$children"

  cp -a "$stage/." "$PREFIX/"
  if [[ ! -f "$PREFIX/assets/geoip/sg-country-geoip.dat" ]]; then
    [[ -n "$ASSETS_RECOVERY_DIR" && -d "$ASSETS_RECOVERY_DIR" ]] || fail "preserved assets are unavailable"
    rm -rf "$PREFIX/assets"
    cp -a "$ASSETS_RECOVERY_DIR" "$PREFIX/assets"
  fi
  chmod 0755 "$PREFIX"
  find "$PREFIX" \
    \( -path "$PREFIX/.venv" -o -path "$PREFIX/assets" -o -path "$AWG3_ROOT" \) -prune -o \
    -exec chown root:root {} +
  find "$PREFIX" \
    \( -path "$PREFIX/.venv" -o -path "$PREFIX/assets" -o -path "$AWG3_ROOT" \) -prune -o \
    -type d -exec chmod 0755 {} +
  find "$PREFIX" \
    \( -path "$PREFIX/.venv" -o -path "$PREFIX/assets" -o -path "$AWG3_ROOT" \) -prune -o \
    -type f -exec chmod 0644 {} +
  find "$PREFIX/deploy" -maxdepth 1 -type f -name '*.sh' -exec chmod 0755 {} + 2>/dev/null || true
  if [[ "$SYSTEM_ROOT" == / ]]; then
    chmod -R a+rX "$PREFIX/.venv"
  fi

  [[ -f "$PREFIX/assets/geoip/sg-country-geoip.dat" ]] || fail "country GeoIP asset disappeared during Update"
  local assets_after
  assets_after="$(fingerprint_tree_relative "$PREFIX/assets")"
  [[ -n "$ASSETS_FINGERPRINT" && "$assets_after" == "$ASSETS_FINGERPRINT" ]] || fail "local assets changed during panel-only Update"
  printf '[SG-Gateway Update] Local assets preserved: OK\n'

  runuser -u sg-gateway -- test -r "$PREFIX/app/main.py"
  runuser -u sg-gateway -- test -x "$PREFIX/.venv/bin/python"
  runuser -u sg-gateway -- "$PREFIX/.venv/bin/python" -c \
    'import flask, jinja2, waitress; print("Python runtime: OK")'

  migrate_panel_wsgi_service
}

restart_panel() {
  systemctl start "$HOSTD_SERVICE"
  for _ in $(seq 1 30); do
    curl -fsS --max-time 2 http://127.0.0.1:8090/health >/dev/null 2>&1 && break
    sleep 1
  done
  curl -fsS --max-time 3 http://127.0.0.1:8090/health >/dev/null

  systemctl start "$PANEL_SERVICE"
  for _ in $(seq 1 30); do
    curl -fsS --max-time 2 http://127.0.0.1:18080/health >/dev/null 2>&1 && break
    sleep 1
  done
  curl -fsS --max-time 3 http://127.0.0.1:18080/health >/dev/null
  SERVICES_STOPPED=0
}

run_stage3a_migration() {
  [[ -n "$MIGRATION_SOURCE_DIR" && -d "$MIGRATION_SOURCE_DIR/vendor/cores" ]] || \
    fail "verified Stage3A migration source is unavailable"
  validate_runtime_sources "$MIGRATION_SOURCE_DIR/vendor/cores"
  PYTHONPATH="$PREFIX:$PREFIX/hostd" \
  SG_GATEWAY_APP_ROOT="$PREFIX" \
  SG_GATEWAY_DATA_DIR="$DATA_DIR" \
  "$PREFIX/.venv/bin/python" -B -m app.maintenance.awg31_stage3a migrate \
    --source-root "$MIGRATION_SOURCE_DIR" \
    --root "$SYSTEM_ROOT" \
    --database "$DATABASE"
}

verify_final() {
  local before after
  local protected_paths=()

  verify_credentials_transition "$BACKUP_DIR/credentials-before.json" || \
    fail "Clients/credentials changed outside the AWG31 migration allowance"

  before="$(cat "$BACKUP_DIR/letsencrypt-before.sha256")"
  after="$(fingerprint_paths "$LETSENCRYPT_DIR")"
  [[ "$before" == "$after" ]] || fail "/etc/letsencrypt changed during Update"

  mapfile -t protected_paths < "$BACKUP_DIR/preserved-runtime-paths.txt"
  before="$(cat "$BACKUP_DIR/protected-runtime-before.sha256")"
  after="$(fingerprint_paths "${protected_paths[@]}")"
  [[ "$before" == "$after" ]] || fail "TLS/AWG2/AWG3 protected runtime changed during Update"

  https_state > "$TEMP_DIR/https-after.env"
  cmp -s "$BACKUP_DIR/https-before.env" "$TEMP_DIR/https-after.env" || \
    fail "HTTPS certificate state changed during Update"

  before="$(cat "$BACKUP_DIR/nginx-before.sha256")"
  after="$(fingerprint_paths \
    "$NGINX_CONFIG" \
    "$NGINX_SITE_AVAILABLE" \
    "$NGINX_SITE_ENABLED" \
    "$NGINX_STREAM_CONFIG")"
  [[ "$before" == "$after" ]] || fail "Nginx configuration changed during Update"

  verify_runtime_states_unchanged "$BACKUP_DIR/service-state.tsv"
  nginx -t >/dev/null

  # shellcheck disable=SC1090
  source "$BACKUP_DIR/https-before.env"
  if [[ "${HTTPS_READY:-0}" == "1" ]]; then
    curl --noproxy '*' -fsS --max-time 15 \
      --resolve "${HTTPS_DOMAIN}:${PANEL_PORT}:127.0.0.1" \
      "https://${HTTPS_DOMAIN}:${PANEL_PORT}/health" >/dev/null
  else
    curl -fsS --max-time 8 "http://127.0.0.1:${PANEL_PORT}/health" >/dev/null
  fi

  systemctl is-active --quiet "$HOSTD_SERVICE"
  systemctl is-active --quiet "$PANEL_SERVICE"
  systemctl is-active --quiet nginx.service
  [[ "$(installed_panel_wsgi_target)" == "$PANEL_PRODUCTION_WSGI" ]] || \
    fail "panel service is not running the production WSGI entrypoint"
}

bind_panel_update_state() {
  [[ "$SOURCE_COMMIT" =~ ^[0-9a-f]{40}$ ]] || fail "source commit is unavailable after deployment"

  local new_version
  new_version="$(tr -d '\r\n' < "$PREFIX/VERSION")"
  if [[ "$SYSTEM_ROOT" == / ]]; then
    install -d -m 0750 -o root -g sg-gateway "$(dirname "$PANEL_UPDATE_STATE")"
  else
    install -d -m 0750 "$(dirname "$PANEL_UPDATE_STATE")"
  fi

  PYTHONPATH="$PREFIX:$PREFIX/hostd" \
  SG_GATEWAY_APP_ROOT="$PREFIX" \
  SG_GATEWAY_PANEL_UPDATE_STATE="$PANEL_UPDATE_STATE" \
  "$PREFIX/.venv/bin/python" -B - \
    "$SOURCE_COMMIT" "$new_version" "$BACKUP_DIR" "$BRANCH" "$SYSTEM_ROOT" <<'PYPANELSTATE'
import json
import os
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

from app.maintenance.panel_updates import source_fingerprint

commit = sys.argv[1].strip().lower()
version = sys.argv[2].strip()
backup = Path(sys.argv[3]).name
channel = sys.argv[4].strip()
system_root = sys.argv[5]
root = Path(os.environ["SG_GATEWAY_APP_ROOT"])
state_path = Path(os.environ["SG_GATEWAY_PANEL_UPDATE_STATE"])

if not re.fullmatch(r"[0-9a-f]{40}", commit):
    raise SystemExit("invalid source commit")

fingerprint = source_fingerprint(root)
if not re.fullmatch(r"[0-9a-f]{64}", fingerprint):
    raise SystemExit("invalid deployed source fingerprint")

payload = {
    "commit": commit,
    "version": version,
    "channel": channel,
    "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    "backup": backup,
    "source_fingerprint": fingerprint,
}
state_path.parent.mkdir(parents=True, exist_ok=True)
temporary = state_path.with_name(state_path.name + ".new")
temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
os.chmod(temporary, 0o640)
if system_root == "/":
    shutil.chown(temporary, user="root", group="sg-gateway")
os.replace(temporary, state_path)
print(f"Panel Update baseline: {commit[:12]} ({channel})")
PYPANELSTATE

  runuser -u sg-gateway -- test -r "$PANEL_UPDATE_STATE"
}

main() {
  printf '\n%s[SG-Gateway Update]%s Dedicated panel-only Update\n' "$CYAN" "$RESET"
  printf '[SG-Gateway Update] This mode does NOT install packages, Certbot, Nginx or VPN cores.\n\n'

  run_stage 1 "Проверка установленного SG-Gateway и HTTPS" preflight

  # Download and validate the candidate before any server mutation.
  prepare_source

  run_stage 2 "Safety Backup: SG state + TLS + AWG3 runtime" create_safety_backup
  run_stage 3 "Обновление исходников SG-Gateway + WSGI migration" deploy_source "$SOURCE_DIR"
  run_stage 4 "Python/UI проверка без изменения runtime" validate_deployed_panel
  run_stage 5 "Перезапуск только panel + hostd" restart_panel
  run_stage 6 "AWG31 Stage3A migration внутри Update transaction" run_stage3a_migration
  run_stage 7 "Проверка HTTPS, credentials, Nginx и runtime" verify_final
  bind_panel_update_state

  if ! prune_safety_backups "$BACKUP_KEEP"; then
    printf '%s[SG-Gateway Update] WARNING:%s old Safety Backup retention cleanup failed; update itself is already verified.
'       "$YELLOW" "$RESET" >&2
  fi

  UPDATE_FINISHED=1
  trap - ERR INT TERM
  local new_version
  new_version="$(tr -d '\r\n' < "$PREFIX/VERSION")"

  printf '\n%s[SG-Gateway Update] ============================================================%s\n' "$GREEN" "$RESET"
  printf '%s[SG-Gateway Update] SG-Gateway safely updated.%s\n' "$GREEN" "$RESET"
  printf '[SG-Gateway Update] VERSION: %s\n' "$new_version"
  printf '[SG-Gateway Update] Safety Backup: %s\n' "$BACKUP_DIR"
  printf '[SG-Gateway Update] TLS certificates/Nginx/AWG3 runtime/VPN cores were not modified.\n'
  printf '[SG-Gateway Update] ============================================================\n'
}

if [[ ${SG_GATEWAY_UPDATE_CORE_LIBRARY_ONLY:-0} != 1 ]]; then
  trap on_error ERR
  trap 'exit 130' INT TERM
  trap cleanup EXIT
  main "$@"
fi
