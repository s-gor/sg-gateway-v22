from __future__ import annotations

import argparse
import os
import stat
import sys
from pathlib import Path


BRIDGE_SERVICE = "sg-infosec-management-bridge.service"
GUARD_ENVIRONMENT = (
    "Environment=SG_INFOSEC_GUARD_SETTINGS=/var/lib/sg-gateway/infosec/guard.json",
    "Environment=SG_INFOSEC_REPUTATION_FILE=/var/lib/sg-gateway/infosec/reputation.json",
    "Environment=SG_INFOSEC_ALERTS_FILE=/var/lib/sg-gateway/infosec/alerts.jsonl",
)
BRIDGE_PRESTART = (
    "ExecStartPre=-+/opt/sg-gateway/deploy/"
    "install-sg-infosec-management-bridge.sh"
)


def _section_index(lines: list[str], name: str) -> int:
    try:
        return lines.index(f"[{name}]")
    except ValueError as exc:
        raise ValueError(f"panel unit lacks [{name}]") from exc


def _insert_before_trailing_blanks(section: list[str], value: str) -> None:
    index = len(section)
    while index > 0 and not section[index - 1].strip():
        index -= 1
    section.insert(index, value)


def _ensure_dependency(section: list[str], directive: str) -> None:
    prefix = directive + "="
    indices = [index for index, line in enumerate(section) if line.startswith(prefix)]
    if not indices:
        _insert_before_trailing_blanks(section, f"{directive}={BRIDGE_SERVICE}")
        return

    index = indices[0]
    values = section[index].split("=", 1)[1].split()
    if BRIDGE_SERVICE not in values:
        values.append(BRIDGE_SERVICE)
        section[index] = prefix + " ".join(values)


def _is_managed_service_line(line: str) -> bool:
    if line == BRIDGE_PRESTART:
        return True
    return any(
        line.startswith(environment.split("=", 2)[0] + "=" + environment.split("=", 2)[1] + "=")
        for environment in GUARD_ENVIRONMENT
    )


def _migrated_body(original: str) -> str:
    lines = original.splitlines()
    unit_index = _section_index(lines, "Unit")
    service_index = _section_index(lines, "Service")
    if service_index <= unit_index:
        raise ValueError("panel unit sections are out of order")

    service_end = next(
        (
            index
            for index in range(service_index + 1, len(lines))
            if lines[index].startswith("[") and lines[index].endswith("]")
        ),
        len(lines),
    )

    before_unit = lines[: unit_index + 1]
    unit_section = lines[unit_index + 1 : service_index]
    service_header = [lines[service_index]]
    service_section = lines[service_index + 1 : service_end]
    after_service = lines[service_end:]

    _ensure_dependency(unit_section, "After")
    _ensure_dependency(unit_section, "Wants")

    managed_environment_prefixes = tuple(
        value.split("=", 2)[0] + "=" + value.split("=", 2)[1] + "="
        for value in GUARD_ENVIRONMENT
    )
    service_section = [
        line
        for line in service_section
        if line != BRIDGE_PRESTART
        and not line.startswith(managed_environment_prefixes)
    ]
    exec_start = next(
        (
            index
            for index, line in enumerate(service_section)
            if line.startswith("ExecStart=")
        ),
        None,
    )
    if exec_start is None:
        raise ValueError("panel unit lacks ExecStart")

    for value in (*GUARD_ENVIRONMENT, BRIDGE_PRESTART):
        service_section.insert(exec_start, value)
        exec_start += 1

    migrated = (
        before_unit
        + unit_section
        + service_header
        + service_section
        + after_service
    )
    return "\n".join(migrated) + "\n"


def migrate_unit(path: str | os.PathLike[str]) -> bool:
    unit = Path(path)
    original = unit.read_text(encoding="utf-8")
    migrated = _migrated_body(original)
    if migrated == original:
        return False

    information = unit.stat()
    temporary = unit.with_name(f".{unit.name}.sg-infosec-new")
    try:
        temporary.write_text(migrated, encoding="utf-8")
        os.chmod(temporary, stat.S_IMODE(information.st_mode))
        os.chown(temporary, information.st_uid, information.st_gid)
        os.replace(temporary, unit)
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass
    return True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Add SG InfoSec integration to an installed SG-Gateway systemd unit."
    )
    parser.add_argument("unit", type=Path)
    arguments = parser.parse_args(argv)
    try:
        changed = migrate_unit(arguments.unit)
    except (OSError, ValueError) as exc:
        print(f"SG InfoSec panel unit migration failed: {exc}", file=sys.stderr)
        return 1
    print("SG InfoSec panel unit migration: " + ("updated" if changed else "current"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
