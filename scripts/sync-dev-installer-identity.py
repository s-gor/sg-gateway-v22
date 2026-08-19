#!/usr/bin/env python3
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VERSION_FILE = ROOT / "VERSION"
INSTALLER = ROOT / "install.sh"


def _replace_exact_count(text: str, pattern: str, replacement: str, expected: int, label: str) -> str:
    updated, count = re.subn(pattern, replacement, text, flags=re.MULTILINE)
    if count != expected:
        raise SystemExit(f"{label}: expected {expected} match(es), found {count}")
    return updated


def normalized_installer(text: str, version: str) -> str:
    match = re.fullmatch(r"0\.1\.0-(\d{3})\.(\d{2})", version)
    if match is None:
        raise SystemExit(f"Unsupported SG-Gateway VERSION format: {version!r}")
    token = "".join(match.groups())

    text = _replace_exact_count(
        text,
        r'^VERSION="[^"]+"$',
        f'VERSION="{version}"',
        1,
        "installer VERSION",
    )
    text = _replace_exact_count(
        text,
        r'^INSTALLER_BUILD="[^"]+"$',
        f'INSTALLER_BUILD="{token}-full-clean-dual-stack"',
        1,
        "installer build id",
    )
    text = _replace_exact_count(
        text,
        r'^INSTALL_LOG="/var/log/sg-gateway-installer-[^"]+\.log"$',
        f'INSTALL_LOG="/var/log/sg-gateway-installer-{token}.log"',
        1,
        "installer log",
    )
    text = _replace_exact_count(
        text,
        r'^RESUME_FILE="/root/sg-gateway-[^"]+-installer-resume\.env"$',
        f'RESUME_FILE="/root/sg-gateway-{token}-installer-resume.env"',
        1,
        "installer resume file",
    )
    text = _replace_exact_count(
        text,
        r'(Запускаю полный мастер SG-Gateway )0\.1\.0-\d{3}\.\d{2}',
        rf'\g<1>{version}',
        1,
        "installer start banner",
    )
    text = _replace_exact_count(
        text,
        r'(Мастер установки SG-Gateway )0\.1\.0-\d{3}\.\d{2}( запущен)',
        rf'\g<1>{version}\g<2>',
        1,
        "installer started banner",
    )
    text = _replace_exact_count(
        text,
        r'before-sg-gateway-\d{3,5}',
        f'before-sg-gateway-{token}',
        2,
        "installer backup suffixes",
    )
    text = _replace_exact_count(
        text,
        r'SG-Gateway (?:021|V22) vendor bundle:',
        'SG-Gateway V22 vendor bundle:',
        1,
        "vendor bundle label",
    )

    required = (
        f'VERSION="{version}"',
        f'INSTALLER_BUILD="{token}-full-clean-dual-stack"',
        f'INSTALL_LOG="/var/log/sg-gateway-installer-{token}.log"',
        f'RESUME_FILE="/root/sg-gateway-{token}-installer-resume.env"',
        f'Запускаю полный мастер SG-Gateway {version}',
        f'Мастер установки SG-Gateway {version} запущен',
        f'before-sg-gateway-{token}',
        'SG-Gateway V22 vendor bundle:',
    )
    missing = [marker for marker in required if marker not in text]
    if missing:
        raise SystemExit("Installer identity validation failed: " + ", ".join(missing))
    if text.count(f'before-sg-gateway-{token}') != 2:
        raise SystemExit("Installer identity validation failed: expected exactly two active backup suffixes")
    return text


def main() -> int:
    check_only = sys.argv[1:] == ["--check"]
    if sys.argv[1:] not in ([], ["--check"]):
        raise SystemExit("usage: sync-dev-installer-identity.py [--check]")

    version = VERSION_FILE.read_text(encoding="utf-8").strip()
    original = INSTALLER.read_text(encoding="utf-8")
    updated = normalized_installer(original, version)

    if check_only:
        if updated != original:
            raise SystemExit("install.sh identity is out of sync with VERSION")
        print(f"Installer identity: OK ({version})")
        return 0

    if updated != original:
        INSTALLER.write_text(updated, encoding="utf-8", newline="\n")
        print(f"Installer identity synchronized to {version}")
    else:
        print(f"Installer identity already synchronized to {version}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
