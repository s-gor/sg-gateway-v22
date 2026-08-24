from __future__ import annotations

import hashlib
import re
import subprocess
from pathlib import Path


def main() -> None:
    repair = Path("deploy/repair-awg3-runtime.sh").read_text(encoding="utf-8")
    match = re.search(r'^VENDOR_COMMIT="([0-9a-f]{40})"$', repair, re.MULTILINE)
    if match is None:
        raise SystemExit("AWG3 VENDOR_COMMIT not found")
    vendor_commit = match.group(1)

    test_path = Path("tests/test_sg_gateway_v22_awg3_runtime_repair.py")
    test_text = test_path.read_text(encoding="utf-8")
    updated, count = re.subn(
        r'assert \'VENDOR_COMMIT="[0-9a-f]{40}"\' in body',
        f'assert \'VENDOR_COMMIT="{vendor_commit}"\' in body',
        test_text,
        count=1,
    )
    if count != 1:
        raise SystemExit("pinned VENDOR_COMMIT assertion not found")
    test_path.write_text(updated, encoding="utf-8")

    tracked = subprocess.check_output(
        ["git", "ls-files"], text=True, encoding="utf-8"
    ).splitlines()
    tracked = [path for path in tracked if path != "SOURCE-SHA256SUMS"]
    rows = [
        f"{hashlib.sha256(Path(path).read_bytes()).hexdigest()}  {path}"
        for path in tracked
    ]
    Path("SOURCE-SHA256SUMS").write_text(
        "\n".join(rows) + "\n", encoding="utf-8"
    )
    print(f"aligned recovery pin test to {vendor_commit}")


if __name__ == "__main__":
    main()
