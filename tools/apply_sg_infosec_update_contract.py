#!/usr/bin/env python3
from pathlib import Path


path = Path("deploy/update-from-github-core.sh")
body = path.read_text(encoding="utf-8")

replacements = [
    (
        'AWG31_SERVICE="sg-gateway-awg31.service"\nAWG2_CONFIG=',
        'AWG31_SERVICE="sg-gateway-awg31.service"\n'
        'INFOSEC_BRIDGE_SERVICE="sg-infosec-management-bridge.service"\n'
        'INFOSEC_BRIDGE_SOURCE="$(system_path /etc/sg-infosec/sources.d/sg-gateway-management.yaml)"\n'
        'INFOSEC_BRIDGE_UNIT="$(system_path /etc/systemd/system/sg-infosec-management-bridge.service)"\n'
        'INFOSEC_BRIDGE_TMPFILES="$(system_path /usr/lib/tmpfiles.d/sg-infosec-management-bridge.conf)"\n'
        'AWG2_CONFIG=',
    ),
    (
        '    sg-gateway-singbox.service "$HOSTD_SERVICE" "$PANEL_SERVICE"; do',
        '    sg-gateway-singbox.service "$HOSTD_SERVICE" "$PANEL_SERVICE" "$INFOSEC_BRIDGE_SERVICE"; do',
    ),
    (
        '      "$PANEL_SERVICE"|"$HOSTD_SERVICE"|"$AWG31_SERVICE") continue ;;',
        '      "$PANEL_SERVICE"|"$HOSTD_SERVICE"|"$AWG31_SERVICE"|"$INFOSEC_BRIDGE_SERVICE") continue ;;',
    ),
    (
        '    etc/systemd/system/sg-gateway-awg31.service; do',
        '    etc/systemd/system/sg-gateway-awg31.service \\\n'
        '    etc/sg-infosec/sources.d/sg-gateway-management.yaml \\\n'
        '    etc/systemd/system/sg-infosec-management-bridge.service \\\n'
        '    usr/lib/tmpfiles.d/sg-infosec-management-bridge.conf; do',
    ),
    (
        '  systemctl stop "$PANEL_SERVICE" "$HOSTD_SERVICE" "$AWG3_SERVICE" "$AWG31_SERVICE" >/dev/null 2>&1 || true',
        '  systemctl stop "$PANEL_SERVICE" "$HOSTD_SERVICE" "$INFOSEC_BRIDGE_SERVICE" "$AWG3_SERVICE" "$AWG31_SERVICE" >/dev/null 2>&1 || true',
    ),
    (
        '    "$AWG2_UNIT" \\\n    "$AWG3_UNIT" \\\n    "$AWG31_UNIT"; do',
        '    "$AWG2_UNIT" \\\n'
        '    "$AWG3_UNIT" \\\n'
        '    "$AWG31_UNIT" \\\n'
        '    "$INFOSEC_BRIDGE_SOURCE" \\\n'
        '    "$INFOSEC_BRIDGE_UNIT" \\\n'
        '    "$INFOSEC_BRIDGE_TMPFILES"; do',
    ),
]

for old, new in replacements:
    count = body.count(old)
    if count != 1:
        raise SystemExit(f"update-core patch anchor count={count}: {old[:100]!r}")
    body = body.replace(old, new, 1)

path.write_text(body, encoding="utf-8")
