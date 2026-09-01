#!/usr/bin/env python3
from pathlib import Path


path = Path("deploy/update-from-github-core.sh")
body = path.read_text(encoding="utf-8")
replacements = [
    (
        'INFOSEC_BRIDGE_SERVICE="sg-infosec-management-bridge.service"\n',
        'INFOSEC_SERVICE="sg-infosec.service"\nINFOSEC_BRIDGE_SERVICE="sg-infosec-management-bridge.service"\n',
    ),
    (
        '  tar -C "$SYSTEM_ROOT" -xpf "$BACKUP_DIR/state.tar"\n  systemctl daemon-reload >/dev/null 2>&1 || true\n',
        '  tar -C "$SYSTEM_ROOT" -xpf "$BACKUP_DIR/state.tar"\n'
        '  systemctl daemon-reload >/dev/null 2>&1 || true\n'
        '  if systemctl is-active --quiet "$INFOSEC_SERVICE"; then\n'
        '    systemctl restart "$INFOSEC_SERVICE" >/dev/null 2>&1 || true\n'
        '  fi\n',
    ),
]
for old, new in replacements:
    count = body.count(old)
    if count != 1:
        raise SystemExit(f"rollback reload patch anchor count={count}: {old!r}")
    body = body.replace(old, new, 1)
path.write_text(body, encoding="utf-8")
