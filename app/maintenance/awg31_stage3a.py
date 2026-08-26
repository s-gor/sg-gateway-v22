from __future__ import annotations

import argparse
import contextlib
import json
import os
import shutil
import sqlite3
import tempfile
from pathlib import Path

from app.maintenance.awg31_stage3a_common import (
    AWG3_GO_FILE,
    AWG3_GO_SHA256,
    AWG3_TOOLS_FILE,
    AWG3_TOOLS_SHA256,
    AWG31_GO_FILE,
    AWG31_GO_SHA256,
    AWG31_TOOLS_FILE,
    AWG31_TOOLS_SHA256,
    DEPLOY_FILES,
    ENGINE_ID,
    INTERFACE,
    SERVICE,
    Layout,
    MigrationResult,
    OSBoundary,
    Replacement,
    SubprocessOS,
)
from app.maintenance.awg31_stage3a_data import DataMixin
from app.maintenance.awg31_stage3a_runtime import RuntimeMixin


class Stage3AInstaller(RuntimeMixin, DataMixin):
    def __init__(
        self,
        *,
        source_root: Path,
        root: Path = Path("/"),
        os_boundary: OSBoundary | None = None,
    ) -> None:
        self.source_root = source_root.resolve()
        self.layout = Layout(root.resolve())
        self.os = os_boundary or SubprocessOS()
        self.source_vendor = self.source_root / "vendor/cores"
        self.source_deploy = self.source_root / "deploy"

    @staticmethod
    def _replace(target: Path, staged: Path, backups: Path) -> Replacement:
        target.parent.mkdir(parents=True, exist_ok=True)
        backup: Path | None = None
        if target.exists() or target.is_symlink():
            backup = backups / f"{len(list(backups.iterdir())):04d}"
            os.replace(target, backup)
        os.replace(staged, target)
        return Replacement(target, backup)

    @staticmethod
    def _rollback(replacements: list[Replacement]) -> None:
        for replacement in reversed(replacements):
            target = replacement.target
            if target.is_dir() and not target.is_symlink():
                shutil.rmtree(target, ignore_errors=True)
            else:
                target.unlink(missing_ok=True)
            if replacement.backup is not None and replacement.backup.exists():
                target.parent.mkdir(parents=True, exist_ok=True)
                os.replace(replacement.backup, target)

    def migrate(self, *, database: Path) -> MigrationResult:
        database = database.resolve()
        database.parent.mkdir(parents=True, exist_ok=True)
        work_parent = self.layout.root / ".sg-gateway-stage3a"
        work_parent.mkdir(parents=True, exist_ok=True)
        work = Path(tempfile.mkdtemp(prefix="run-", dir=work_parent))
        backups = work / "backups"
        backups.mkdir()
        replacements: list[Replacement] = []
        connection: sqlite3.Connection | None = None
        committed = False
        preserve_awg3_runtime = (
            self.layout.awg3_runtime.exists()
            or self.layout.awg3_runtime.is_symlink()
        )
        try:
            vendor, deploy = self._copy_install_media(work)
            awg3_runtime = self._build_runtime(
                work=work,
                vendor=vendor,
                tools_file=AWG3_TOOLS_FILE,
                go_file=AWG3_GO_FILE,
                tools_sha=AWG3_TOOLS_SHA256,
                go_sha=AWG3_GO_SHA256,
                name="awg3",
            )
            awg31_runtime = self._build_runtime(
                work=work,
                vendor=vendor,
                tools_file=AWG31_TOOLS_FILE,
                go_file=AWG31_GO_FILE,
                tools_sha=AWG31_TOOLS_SHA256,
                go_sha=AWG31_GO_SHA256,
                name="awg31",
            )
            state, server_private, server_public = self._prepare_state(work, awg31_runtime)

            connection = sqlite3.connect(database)
            connection.execute("PRAGMA foreign_keys = ON")
            connection.execute("BEGIN IMMEDIATE")
            settings = self._settings(connection)
            header_protection_key = self._header_protection_key(connection)
            self._persist_settings(
                connection, settings, server_public, header_protection_key
            )
            created = self._sync_credentials(
                connection, settings, server_public, header_protection_key
            )
            config, peer_count = self._render_configs(
                work=work,
                connection=connection,
                settings=settings,
                header_protection_key=header_protection_key,
                server_private=server_private,
                server_public=server_public,
            )

            if not preserve_awg3_runtime:
                replacements.append(
                    self._replace(self.layout.awg3_runtime, awg3_runtime, backups)
                )
            replacements.append(self._replace(self.layout.awg31_runtime, awg31_runtime, backups))
            replacements.append(self._replace(self.layout.config, config, backups))
            replacements.append(self._replace(self.layout.state, state, backups))
            self.layout.vendor.mkdir(parents=True, exist_ok=True)
            for filename in (
                AWG3_TOOLS_FILE,
                AWG3_GO_FILE,
                AWG31_TOOLS_FILE,
                AWG31_GO_FILE,
            ):
                replacements.append(
                    self._replace(self.layout.vendor / filename, vendor / filename, backups)
                )
            self.layout.deploy.mkdir(parents=True, exist_ok=True)
            for filename in DEPLOY_FILES:
                replacements.append(
                    self._replace(self.layout.deploy / filename, deploy / filename, backups)
                )
            unit_staged = work / SERVICE
            shutil.copy2(self.layout.deploy / SERVICE, unit_staged)
            replacements.append(self._replace(self.layout.unit, unit_staged, backups))

            self.os.run("systemctl", "daemon-reload")
            self.os.run("systemctl", "enable", SERVICE)
            self.os.run("systemctl", "restart", SERVICE)
            if not preserve_awg3_runtime and self.layout.awg3_unit.is_file():
                self.os.run("systemctl", "try-restart", "sg-gateway-awg3.service")
            connection.commit()
            committed = True
            total = connection.execute(
                "SELECT COUNT(*) FROM device_credentials WHERE engine = ?", (ENGINE_ID,)
            ).fetchone()[0]
            return MigrationResult(
                created_credentials=created,
                total_credentials=int(total),
                server_config=self.layout.config / "awg31.conf",
                peer_configs=peer_count,
            )
        except Exception:
            if connection is not None and not committed:
                connection.rollback()
            with contextlib.suppress(RuntimeError):
                self.os.run("systemctl", "disable", "--now", SERVICE)
            self._rollback(replacements)
            with contextlib.suppress(RuntimeError):
                self.os.run("systemctl", "daemon-reload")
            if not preserve_awg3_runtime and self.layout.awg3_unit.is_file():
                with contextlib.suppress(RuntimeError):
                    self.os.run("systemctl", "try-restart", "sg-gateway-awg3.service")
            raise
        finally:
            if connection is not None:
                connection.close()
            shutil.rmtree(work, ignore_errors=True)
            try:
                work_parent.rmdir()
            except OSError:
                pass

    def uninstall(self, *, database: Path, purge_data: bool = False) -> None:
        with contextlib.suppress(RuntimeError):
            self.os.run("systemctl", "disable", "--now", SERVICE)
        with contextlib.suppress(RuntimeError):
            self.os.run("ip", "link", "delete", INTERFACE)
        socket_path = self.layout.under("/var/run/amneziawg/awg31.sock")
        socket_path.unlink(missing_ok=True)
        for path in (
            self.layout.unit,
            self.layout.awg31_runtime,
            self.layout.config,
            self.layout.state,
        ):
            if path.is_dir() and not path.is_symlink():
                shutil.rmtree(path)
            else:
                path.unlink(missing_ok=True)
        with contextlib.suppress(RuntimeError):
            self.os.run("systemctl", "daemon-reload")
        if purge_data and database.is_file():
            with sqlite3.connect(database) as connection:
                connection.execute("BEGIN IMMEDIATE")
                connection.execute(
                    "DELETE FROM device_credentials WHERE engine = ?", (ENGINE_ID,)
                )
                connection.commit()


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="SG-Gateway AWG31 stage 3A lifecycle")
    parser.add_argument("command", choices=("migrate", "uninstall"))
    parser.add_argument("--source-root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--root", type=Path, default=Path("/"))
    parser.add_argument("--database", type=Path, default=Path("/var/lib/sg-gateway/sg-gateway.sqlite"))
    parser.add_argument("--purge-data", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    installer = Stage3AInstaller(source_root=args.source_root, root=args.root)
    if args.command == "migrate":
        result = installer.migrate(database=args.database)
        print(
            json.dumps(
                {
                    "created_credentials": result.created_credentials,
                    "total_credentials": result.total_credentials,
                    "server_config": str(result.server_config),
                    "peer_configs": result.peer_configs,
                },
                sort_keys=True,
            )
        )
    else:
        installer.uninstall(database=args.database, purge_data=args.purge_data)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
