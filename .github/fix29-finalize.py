from __future__ import annotations

import hashlib
import re
import subprocess
import sys
from pathlib import Path

mode = sys.argv[1] if len(sys.argv) > 1 else "inventory"
root = Path(".")

if mode == "inventory":
    files = subprocess.check_output(["git", "ls-files"], text=True, encoding="utf-8").splitlines()
    rows: list[str] = []
    for rel in sorted(files):
        if rel == "SOURCE-SHA256SUMS":
            continue
        rows.append(f"{hashlib.sha256(Path(rel).read_bytes()).hexdigest()}  {rel}")
    Path("SOURCE-SHA256SUMS").write_text("\n".join(rows) + "\n", encoding="utf-8", newline="\n")
    print(f"SOURCE_INVENTORY={len(rows)}")
    raise SystemExit(0)

if mode == "git-blobs":
    expected: dict[str, str] = {}
    for raw in Path("SOURCE-SHA256SUMS").read_text(encoding="utf-8").splitlines():
        match = re.fullmatch(r"([0-9a-f]{64})  (.+)", raw)
        if match is None:
            raise SystemExit(f"invalid checksum row: {raw!r}")
        expected[match.group(2)] = match.group(1)
    tracked = set(subprocess.check_output(["git", "ls-files"], text=True, encoding="utf-8").splitlines())
    tracked.discard("SOURCE-SHA256SUMS")
    if tracked != set(expected):
        raise SystemExit(f"inventory mismatch missing={sorted(tracked-set(expected))[:10]} extra={sorted(set(expected)-tracked)[:10]}")
    for path in sorted(tracked):
        actual = hashlib.sha256(subprocess.check_output(["git", "show", f"HEAD:{path}"])).hexdigest()
        if actual != expected[path]:
            raise SystemExit(f"git blob mismatch: {path}")
    print(f"GIT_BLOB_INTEGRITY_OK={len(tracked)}")
    raise SystemExit(0)

raise SystemExit(f"unknown mode: {mode}")
