#!/usr/bin/env bash
set -Eeuo pipefail

SOURCE="$RUNNER_TEMP/integrate-awg31-final.sh"
PATCHED="$RUNNER_TEMP/integrate-awg31-final-v2.sh"
cp "$SOURCE" "$PATCHED"

python3 - "$PATCHED" <<'PY'
import sys
from pathlib import Path

path = Path(sys.argv[1])
text = path.read_text(encoding="utf-8")
old = 'if path == Path("SOURCE-SHA256SUMS") or not path.is_file():'
new = '''if path in {
        Path("SOURCE-SHA256SUMS"),
        Path(".github/workflows/dev-02206-guard.yml"),
    } or not path.is_file():'''
if text.count(old) != 1:
    raise SystemExit("unable to patch replacement exclusion")
text = text.replace(old, new, 1)
old = 'if path in {Path("SOURCE-SHA256SUMS"), Path("tests/test_sg_gateway_v22_awg31_vendor_runtime.py")} or not path.is_file():'
new = '''if path in {
        Path("SOURCE-SHA256SUMS"),
        Path("tests/test_sg_gateway_v22_awg31_vendor_runtime.py"),
        Path(".github/workflows/dev-02206-guard.yml"),
    } or not path.is_file():'''
if text.count(old) != 1:
    raise SystemExit("unable to patch stale-reference exclusion")
text = text.replace(old, new, 1)
path.write_text(text, encoding="utf-8")
PY

bash "$PATCHED"
