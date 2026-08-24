#!/usr/bin/env bash
set -Eeuo pipefail

BASE_SHA="$(git rev-parse HEAD)"
WORK="$RUNNER_TEMP/awg31-final-build"
OUT="$RUNNER_TEMP/awg31-final-artifacts"
TOOLS_NAME="amneziawg-tools-3.1.20260812.tar.gz"
GO_NAME="amneziawg-go-linux-amd64-v3.1.20260814"
OLD_TOOLS_NAME="amneziawg-tools-3.0.20260805.tar.gz"
OLD_GO_NAME="amneziawg-go-linux-amd64-v3.0.0"
OLD_TOOLS_SHA="090f9383532822a756d078890b447e00af7f46bd30a10f9f47c46d633d807b19"
OLD_GO_SHA="131110027db6d5dc0e35b19eb5b8a2692676081366c34112088dc68bbb050bcd"

rm -rf "$WORK" "$OUT"
mkdir -p "$WORK" "$OUT"

git clone --depth 1 --branch v3.1.20260814 \
  https://github.com/amnezia-vpn/amneziawg-go.git "$WORK/amneziawg-go"
make -C "$WORK/amneziawg-go" amneziawg-go
install -m 0755 "$WORK/amneziawg-go/amneziawg-go" "$OUT/$GO_NAME"

git clone --depth 1 --branch v3.1.20260812 \
  https://github.com/amnezia-vpn/amneziawg-tools.git "$WORK/amneziawg-tools-3.1.20260812"
make -C "$WORK/amneziawg-tools-3.1.20260812/src" PLATFORM=linux -j"$(nproc)"
"$WORK/amneziawg-tools-3.1.20260812/src/wg" --version
tar --exclude=.git -C "$WORK" -czf "$OUT/$TOOLS_NAME" amneziawg-tools-3.1.20260812

NEW_TOOLS_SHA="$(sha256sum "$OUT/$TOOLS_NAME" | awk '{print $1}')"
NEW_GO_SHA="$(sha256sum "$OUT/$GO_NAME" | awk '{print $1}')"
export TOOLS_NAME GO_NAME OLD_TOOLS_NAME OLD_GO_NAME
export OLD_TOOLS_SHA OLD_GO_SHA NEW_TOOLS_SHA NEW_GO_SHA
printf '%s  %s\n' "$NEW_TOOLS_SHA" "$TOOLS_NAME"
printf '%s  %s\n' "$NEW_GO_SHA" "$GO_NAME"

rm -f "vendor/cores/$OLD_TOOLS_NAME" "vendor/cores/$OLD_GO_NAME"
install -m 0644 "$OUT/$TOOLS_NAME" "vendor/cores/$TOOLS_NAME"
install -m 0755 "$OUT/$GO_NAME" "vendor/cores/$GO_NAME"

python3 - <<'PY'
import os
import subprocess
from pathlib import Path

replacements = (
    (os.environ["OLD_TOOLS_NAME"], os.environ["TOOLS_NAME"]),
    (os.environ["OLD_GO_NAME"], os.environ["GO_NAME"]),
    ("3.0.20260805", "3.1.20260812"),
    ("AmneziaWG 3.0", "AmneziaWG 3.1"),
    ("AWG 3.0", "AWG 3.1"),
    (os.environ["OLD_TOOLS_SHA"], os.environ["NEW_TOOLS_SHA"]),
    (os.environ["OLD_GO_SHA"], os.environ["NEW_GO_SHA"]),
)
changed = []
for raw in subprocess.check_output(["git", "ls-files", "-z"]).split(b"\0"):
    if not raw:
        continue
    path = Path(raw.decode("utf-8"))
    if path == Path("SOURCE-SHA256SUMS") or not path.is_file():
        continue
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        continue
    updated = text
    for old, new in replacements:
        updated = updated.replace(old, new)
    if updated != text:
        path.write_text(updated, encoding="utf-8")
        changed.append(str(path))
print("updated references:")
print("\n".join(changed) or "(none)")
PY

python3 - <<'PY'
import hashlib
import os
from pathlib import Path

sums = Path("vendor/cores/SHA256SUMS")
excluded = {
    os.environ["OLD_TOOLS_NAME"],
    os.environ["OLD_GO_NAME"],
    os.environ["TOOLS_NAME"],
    os.environ["GO_NAME"],
}
retained = []
for line in sums.read_text(encoding="utf-8").splitlines():
    if not line.strip():
        continue
    name = line.split("  ", 1)[1]
    if name not in excluded:
        retained.append(line)
for name in (os.environ["TOOLS_NAME"], os.environ["GO_NAME"]):
    path = Path("vendor/cores") / name
    retained.append(f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {name}")
sums.write_text("\n".join(retained) + "\n", encoding="utf-8")
PY

python3 - <<'PY'
from pathlib import Path

versions = Path("vendor/cores/VERSIONS.env")
lines = versions.read_text(encoding="utf-8").splitlines()
keys = {
    "AMNEZIAWG3_TOOLS_VERSION": "3.1.20260812",
    "AMNEZIAWG3_GO_VERSION": "3.1.20260814",
}
present = set()
updated = []
for line in lines:
    key = line.split("=", 1)[0] if "=" in line else ""
    if key in keys:
        updated.append(f"{key}={keys[key]}")
        present.add(key)
    else:
        updated.append(line)
for key, value in keys.items():
    if key not in present:
        updated.append(f"{key}={value}")
versions.write_text("\n".join(updated) + "\n", encoding="utf-8")

notices = Path("vendor/cores/THIRD-PARTY-NOTICES.md")
text = notices.read_text(encoding="utf-8")
marker = "- AmneziaWG 3.1 tools 3.1.20260812"
if marker not in text:
    anchor = "\nThe original upstream licenses"
    addition = (
        "- AmneziaWG 3.1 tools 3.1.20260812 — source archive for the independent AWG3 runtime\n"
        "- AmneziaWG 3.1 userspace 3.1.20260814 — pinned linux/amd64 binary for the independent AWG3 runtime\n"
    )
    text = text.replace(anchor, "\n" + addition + anchor)
    notices.write_text(text, encoding="utf-8")
PY

cat > tests/test_sg_gateway_v22_awg31_vendor_runtime.py <<'PY'
from __future__ import annotations

import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CORES = ROOT / "vendor" / "cores"
TOOLS = "amneziawg-tools-3.1.20260812.tar.gz"
GO = "amneziawg-go-linux-amd64-v3.1.20260814"


def _sums() -> dict[str, str]:
    rows: dict[str, str] = {}
    for line in (CORES / "SHA256SUMS").read_text(encoding="utf-8").splitlines():
        digest, name = line.split("  ", 1)
        rows[name] = digest
    return rows


def test_awg31_vendor_files_are_pinned_and_hashed() -> None:
    sums = _sums()
    for name in (TOOLS, GO):
        path = CORES / name
        assert path.is_file()
        assert hashlib.sha256(path.read_bytes()).hexdigest() == sums[name]


def test_awg30_vendor_payload_is_removed() -> None:
    assert not (CORES / "amneziawg-tools-3.0.20260805.tar.gz").exists()
    assert not (CORES / "amneziawg-go-linux-amd64-v3.0.0").exists()


def test_awg31_versions_are_declared() -> None:
    versions = (CORES / "VERSIONS.env").read_text(encoding="utf-8")
    assert "AMNEZIAWG3_TOOLS_VERSION=3.1.20260812" in versions
    assert "AMNEZIAWG3_GO_VERSION=3.1.20260814" in versions


def test_awg31_repair_uses_new_vendor_runtime() -> None:
    repair = (ROOT / "deploy" / "repair-awg3-runtime.sh").read_text(encoding="utf-8")
    assert TOOLS in repair
    assert GO in repair
    assert "amneziawg-tools-3.0.20260805.tar.gz" not in repair
    assert "amneziawg-go-linux-amd64-v3.0.0" not in repair


def test_awg3_profile_remains_independent_from_awg2() -> None:
    corpus = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (
            ROOT / "deploy" / "sg-gateway-awg3-userspace.sh",
            ROOT / "deploy" / "sg-gateway-awg3.service",
            ROOT / "deploy" / "repair-awg3-runtime.sh",
        )
    )
    assert "/opt/sg-gateway/awg3" in corpus
    assert "sg-gateway-awg3.service" in corpus
    assert "/etc/amnezia/amneziawg/awg3.conf" in corpus
PY

git add -A

python3 - <<'PY'
import os
import subprocess
from pathlib import Path

forbidden = (
    os.environ["OLD_TOOLS_NAME"],
    os.environ["OLD_GO_NAME"],
    "AmneziaWG 3.0",
    "AWG 3.0",
    os.environ["OLD_TOOLS_SHA"],
    os.environ["OLD_GO_SHA"],
)
offenders = []
for raw in subprocess.check_output(["git", "ls-files", "-z"]).split(b"\0"):
    if not raw:
        continue
    path = Path(raw.decode("utf-8"))
    if path in {Path("SOURCE-SHA256SUMS"), Path("tests/test_sg_gateway_v22_awg31_vendor_runtime.py")} or not path.is_file():
        continue
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        continue
    for needle in forbidden:
        if needle in text:
            offenders.append(f"{path}: {needle}")
if offenders:
    raise SystemExit("stale AWG 3.0 references:\n" + "\n".join(offenders))
PY

# Refresh the inventory before the full suite. This is required because the
# upgrade removes two tracked AWG 3.0 payloads and adds two AWG 3.1 payloads.
python3 - <<'PY'
import hashlib
import subprocess
from pathlib import Path

tracked = subprocess.check_output(["git", "ls-files"], text=True, encoding="utf-8").splitlines()
tracked = [path for path in tracked if path != "SOURCE-SHA256SUMS"]
rows = [f"{hashlib.sha256(Path(path).read_bytes()).hexdigest()}  {path}" for path in tracked]
Path("SOURCE-SHA256SUMS").write_text("\n".join(rows) + "\n", encoding="utf-8")
PY
git add SOURCE-SHA256SUMS

bash -n deploy/repair-awg3-runtime.sh
(cd vendor/cores && grep "  $TOOLS_NAME$" SHA256SUMS | sha256sum -c -)
(cd vendor/cores && grep "  $GO_NAME$" SHA256SUMS | sha256sum -c -)

VALIDATE_ROOT="$(mktemp -d /tmp/sg-awg31-final.XXXXXX)"
trap 'rm -rf -- "$VALIDATE_ROOT"' EXIT
mkdir -p "$VALIDATE_ROOT/src" "$VALIDATE_ROOT/runtime/bin"
tar -xzf "vendor/cores/$TOOLS_NAME" -C "$VALIDATE_ROOT/src"
TOOLS_SRC="$(find "$VALIDATE_ROOT/src" -maxdepth 1 -type d -name 'amneziawg-tools-*' -print -quit)"
test -n "$TOOLS_SRC"
make -C "$TOOLS_SRC/src" PLATFORM=linux -j2
make -C "$TOOLS_SRC/src" \
  PLATFORM=linux WITH_WGQUICK=yes WITH_BASHCOMPLETION=no WITH_SYSTEMDUNITS=no \
  PREFIX="$VALIDATE_ROOT/runtime" SYSCONFDIR="$VALIDATE_ROOT/runtime/etc" install
"$VALIDATE_ROOT/runtime/bin/awg" --version | grep '3.1.20260812'
install -m 0755 "vendor/cores/$GO_NAME" "$VALIDATE_ROOT/runtime/bin/amneziawg-go"
test -x "$VALIDATE_ROOT/runtime/bin/amneziawg-go"

python -m pytest \
  tests/test_sg_gateway_v22_awg31_vendor_runtime.py \
  tests/test_sg_gateway_v22_awg3_dual_contract.py \
  tests/test_sg_gateway_v22_awg3_runtime_repair.py \
  tests/test_fix30_awg3_update_preservation.py
python -m pytest tests

# Preserve the staged intended tree if tests modify tracked fixtures.
git restore --worktree .
git clean -fd

git config user.name "github-actions[bot]"
git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
git commit -m "feat: upgrade independent AWG3 runtime to 3.1"
VENDOR_COMMIT="$(git rev-parse HEAD)"

python3 - "$VENDOR_COMMIT" <<'PY'
import re
import sys
from pathlib import Path

commit = sys.argv[1]
path = Path("deploy/repair-awg3-runtime.sh")
text = path.read_text(encoding="utf-8")
updated, count = re.subn(
    r'^VENDOR_COMMIT="[0-9a-f]{40}"$',
    f'VENDOR_COMMIT="{commit}"',
    text,
    count=1,
    flags=re.MULTILINE,
)
if count != 1:
    raise SystemExit("unable to update AWG3 VENDOR_COMMIT")
path.write_text(updated, encoding="utf-8")
PY

git add deploy/repair-awg3-runtime.sh
python3 - <<'PY'
import hashlib
import subprocess
from pathlib import Path

tracked = subprocess.check_output(["git", "ls-files"], text=True, encoding="utf-8").splitlines()
tracked = [path for path in tracked if path != "SOURCE-SHA256SUMS"]
rows = [f"{hashlib.sha256(Path(path).read_bytes()).hexdigest()}  {path}" for path in tracked]
Path("SOURCE-SHA256SUMS").write_text("\n".join(rows) + "\n", encoding="utf-8")
PY
git add SOURCE-SHA256SUMS
git commit -m "fix: pin AWG 3.1 recovery payload"

python3 - <<'PY'
import hashlib
import re
import subprocess
from pathlib import Path

expected = {}
for line_no, raw in enumerate(Path("SOURCE-SHA256SUMS").read_text(encoding="utf-8").splitlines(), 1):
    if not raw.strip():
        continue
    match = re.fullmatch(r"([0-9a-f]{64})  (.+)", raw)
    if match is None:
        raise SystemExit(f"invalid checksum line {line_no}: {raw!r}")
    digest, path = match.groups()
    expected[path] = digest
tracked = set(subprocess.check_output(["git", "ls-files"], text=True, encoding="utf-8").splitlines())
tracked.discard("SOURCE-SHA256SUMS")
if tracked != set(expected):
    raise SystemExit("source checksum inventory mismatch")
for path in sorted(tracked):
    actual = hashlib.sha256(Path(path).read_bytes()).hexdigest()
    if actual != expected[path]:
        raise SystemExit(f"source hash mismatch: {path}")
print(f"Source integrity OK: {len(tracked)} files")
PY

VERSION="$(tr -d '[:space:]' < VERSION)"
PACKAGE="/tmp/SG-Gateway-${VERSION}-DEV-02206-AWG31-FULL.run"
bash build-run.sh "$PACKAGE"
bash "$PACKAGE" --verify-only

test -z "$(git status --porcelain)"
REMOTE_SHA="$(git ls-remote origin refs/heads/dev-02206 | awk '{print $1}')"
test "$REMOTE_SHA" = "$BASE_SHA"
git push origin HEAD:dev-02206

echo "DEV_HEAD=$(git rev-parse HEAD)" >> "$GITHUB_ENV"
