from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

ENGINE_ID = "amneziawg31"
SERVICE = "sg-gateway-awg31.service"
INTERFACE = "awg31"
ENDPOINT = "awg31.internal:587"
DNS = "1.1.1.1"
NETWORK = "10.131.0.0/24"

AWG3_TOOLS_FILE = "amneziawg-tools-3.0.20260805.tar.gz"
AWG3_GO_FILE = "amneziawg-go-linux-amd64-v3.0.0"
AWG31_TOOLS_FILE = "amneziawg-tools-3.1.20260812.tar.gz"
AWG31_GO_FILE = "amneziawg-go-linux-amd64-v3.1.20260814"
AWG3_TOOLS_SHA256 = "090f9383532822a756d078890b447e00af7f46bd30a10f9f47c46d633d807b19"
AWG3_GO_SHA256 = "131110027db6d5dc0e35b19eb5b8a2692676081366c34112088dc68bbb050bcd"
AWG31_TOOLS_SHA256 = "f18592c499c893b1b87b15de9e707ce265585cf2536698975b6ede8156d14ada"
AWG31_GO_SHA256 = "375bc2645df09498aa30215e3b3a09a97626a8e929f409e0edef6564fb8e3110"

DEPLOY_FILES = (
    "sg-gateway-awg31.service",
    "sg-gateway-awg31-userspace.sh",
    "sg-gateway-awg31ctl",
    "repair-awg31-runtime.sh",
    "uninstall-awg31.sh",
)


class OSBoundary(Protocol):
    def run(self, *command: str) -> None: ...


class SubprocessOS:
    def run(self, *command: str) -> None:
        completed = subprocess.run(command, text=True, capture_output=True, check=False)
        if completed.returncode:
            detail = (completed.stderr or completed.stdout or "command failed").strip()
            raise RuntimeError(f"{' '.join(command)}: {detail}")


@dataclass(frozen=True)
class MigrationResult:
    created_credentials: int
    total_credentials: int
    server_config: Path
    peer_configs: int


@dataclass(frozen=True)
class Layout:
    root: Path

    def under(self, value: str) -> Path:
        return self.root / value.lstrip("/")

    @property
    def prefix(self) -> Path:
        return self.under("/opt/sg-gateway")

    @property
    def vendor(self) -> Path:
        return self.prefix / "vendor/cores"

    @property
    def deploy(self) -> Path:
        return self.prefix / "deploy"

    @property
    def awg3_runtime(self) -> Path:
        return self.prefix / "awg3"

    @property
    def awg31_runtime(self) -> Path:
        return self.prefix / "awg31"

    @property
    def config(self) -> Path:
        return self.under("/etc/amnezia/amneziawg/awg31")

    @property
    def peers(self) -> Path:
        return self.config / "peers"

    @property
    def state(self) -> Path:
        return self.under("/var/lib/sg-gateway/awg31")

    @property
    def awg3_unit(self) -> Path:
        return self.under("/etc/systemd/system/sg-gateway-awg3.service")

    @property
    def unit(self) -> Path:
        return self.under(f"/etc/systemd/system/{SERVICE}")


@dataclass
class Replacement:
    target: Path
    backup: Path | None
