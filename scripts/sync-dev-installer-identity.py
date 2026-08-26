#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VERSION_FILE = ROOT / "VERSION"
INSTALLER = ROOT / "install.sh"
UNINSTALLER = ROOT / "deploy" / "full-uninstall-ubuntu.sh"
SOURCE_SUMS = ROOT / "SOURCE-SHA256SUMS"
AWG3_HELPER_CHMOD = 'chmod 0755 "$PREFIX/deploy/sg-gateway-awg3-userspace.sh"'


def _version_token(version: str) -> str:
    match = re.fullmatch(r"0\.1\.0-(\d{3})\.(\d{2})", version)
    if match is None:
        raise SystemExit(f"Unsupported SG-Gateway VERSION format: {version!r}")
    return "".join(match.groups())


def _replace_exact_count(text: str, pattern: str, replacement: str, expected: int, label: str) -> str:
    updated, count = re.subn(pattern, replacement, text, flags=re.MULTILINE)
    if count != expected:
        raise SystemExit(f"{label}: expected {expected} match(es), found {count}")
    return updated


def normalized_installer(text: str, version: str, token: str) -> str:
    text = _replace_exact_count(text, r'^VERSION="[^"]+"$', f'VERSION="{version}"', 1, "installer VERSION")
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

    # systemd executes the AWG3 userspace helper directly. Keep an explicit
    # install-time chmod even when the Git executable bit is already correct,
    # so archive/copy mode drift cannot turn this into status=203/EXEC.
    if AWG3_HELPER_CHMOD not in text:
        anchor = 'chmod 0755 "$PREFIX/deploy/configure-panel-access.sh"'
        if text.count(anchor) != 1:
            raise SystemExit("AWG3 helper chmod: configure-panel-access chmod anchor is not unique")
        text = text.replace(anchor, f"{anchor}\n{AWG3_HELPER_CHMOD}", 1)
    if text.count(AWG3_HELPER_CHMOD) != 1:
        raise SystemExit("AWG3 helper chmod: expected exactly one executable-mode enforcement")

    required = (
        f'VERSION="{version}"',
        f'INSTALLER_BUILD="{token}-full-clean-dual-stack"',
        f'INSTALL_LOG="/var/log/sg-gateway-installer-{token}.log"',
        f'RESUME_FILE="/root/sg-gateway-{token}-installer-resume.env"',
        f'Запускаю полный мастер SG-Gateway {version}',
        f'Мастер установки SG-Gateway {version} запущен',
        f'before-sg-gateway-{token}',
        'SG-Gateway V22 vendor bundle:',
        AWG3_HELPER_CHMOD,
    )
    missing = [marker for marker in required if marker not in text]
    if missing:
        raise SystemExit("Installer identity validation failed: " + ", ".join(missing))
    if text.count(f'before-sg-gateway-{token}') != 2:
        raise SystemExit("Installer identity validation failed: expected exactly two active backup suffixes")
    return text


def normalized_uninstaller(text: str, version: str, token: str) -> str:
    text = _replace_exact_count(
        text,
        r'^UNINSTALL_LOG="/var/log/sg-gateway-full-uninstall-[^"]+\.log"$',
        f'UNINSTALL_LOG="/var/log/sg-gateway-full-uninstall-{token}.log"',
        1,
        "uninstaller log",
    )
    text = _replace_exact_count(
        text,
        r'SG-Gateway 0\.1\.0-\d{3}\.\d{2} · ПОЛНОЕ УДАЛЕНИЕ',
        f'SG-Gateway {version} · ПОЛНОЕ УДАЛЕНИЕ',
        1,
        "uninstaller banner",
    )
    required = (
        f'UNINSTALL_LOG="/var/log/sg-gateway-full-uninstall-{token}.log"',
        f'SG-Gateway {version} · ПОЛНОЕ УДАЛЕНИЕ',
    )
    missing = [marker for marker in required if marker not in text]
    if missing:
        raise SystemExit("Uninstaller identity validation failed: " + ", ".join(missing))
    return text


def refresh_source_integrity() -> None:
    tracked = subprocess.check_output(
        ["git", "ls-files"],
        cwd=ROOT,
        text=True,
        encoding="utf-8",
    ).splitlines()
    tracked = [path for path in tracked if path != SOURCE_SUMS.name]
    rows = [f"{hashlib.sha256((ROOT / path).read_bytes()).hexdigest()}  {path}" for path in tracked]
    SOURCE_SUMS.write_text("\n".join(rows) + "\n", encoding="utf-8", newline="\n")


def main() -> int:
    check_only = sys.argv[1:] == ["--check"]
    if sys.argv[1:] not in ([], ["--check"]):
        raise SystemExit("usage: sync-dev-installer-identity.py [--check]")

    version = VERSION_FILE.read_text(encoding="utf-8").strip()
    token = _version_token(version)
    originals = {
        INSTALLER: INSTALLER.read_text(encoding="utf-8"),
        UNINSTALLER: UNINSTALLER.read_text(encoding="utf-8"),
    }
    updated = {
        INSTALLER: normalized_installer(originals[INSTALLER], version, token),
        UNINSTALLER: normalized_uninstaller(originals[UNINSTALLER], version, token),
    }
    changed = [path for path in originals if updated[path] != originals[path]]

    if check_only:
        if changed:
            names = ", ".join(path.relative_to(ROOT).as_posix() for path in changed)
            raise SystemExit(f"deploy identity is out of sync with VERSION: {names}")
        print(f"Deploy identity: OK ({version})")
        return 0

    for path in changed:
        path.write_text(updated[path], encoding="utf-8", newline="\n")
    refresh_source_integrity()
    if changed:
        names = ", ".join(path.relative_to(ROOT).as_posix() for path in changed)
        print(f"Deploy identity synchronized to {version}: {names}")
    else:
        print(f"Deploy identity already synchronized to {version}")
    print("Source integrity inventory refreshed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
