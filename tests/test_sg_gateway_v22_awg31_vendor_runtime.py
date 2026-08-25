from __future__ import annotations

import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CORES = ROOT / "vendor" / "cores"
TOOLS = "amneziawg-tools-3.1.20260812.tar.gz"
GO = "amneziawg-go-linux-amd64-v3.1.20260814"


def _sums() -> dict[str, str]:
    rows: dict[str, str] = {}
    for line in (CORES / "SHA256SUMS").read_text(encoding="utf-8").splitlines():
        digest, name = line.split("  ", 1)
        rows[name] = digest
    return rows


def test_awg31_vendor_files_are_pinned_and_hashed() -> None:
    sums = _sums()
    for name in (TOOLS, GO):
        path = CORES / name
        assert path.is_file()
        assert hashlib.sha256(path.read_bytes()).hexdigest() == sums[name]


def test_awg30_and_awg31_vendor_payloads_are_both_pinned() -> None:
    assert (CORES / "amneziawg-tools-3.0.20260805.tar.gz").is_file()
    assert (CORES / "amneziawg-go-linux-amd64-v3.0.0").is_file()


def test_awg31_versions_are_declared() -> None:
    versions = (CORES / "VERSIONS.env").read_text(encoding="utf-8")
    assert "AMNEZIAWG3_TOOLS_VERSION=3.0.20260805" in versions
    assert "AMNEZIAWG3_GO_VERSION=3.0.0" in versions
    assert "AMNEZIAWG31_TOOLS_VERSION=3.1.20260812" in versions
    assert "AMNEZIAWG31_GO_VERSION=3.1.20260814" in versions


def test_awg3_repair_stays_on_30_runtime() -> None:
    repair = (ROOT / "deploy" / "repair-awg3-runtime.sh").read_text(encoding="utf-8")
    assert TOOLS not in repair
    assert GO not in repair
    assert "amneziawg-tools-3.0.20260805.tar.gz" in repair
    assert "amneziawg-go-linux-amd64-v3.0.0" in repair


def test_awg3_profile_remains_independent_from_awg2() -> None:
    corpus = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (
            ROOT / "deploy" / "sg-gateway-awg3-userspace.sh",
            ROOT / "deploy" / "sg-gateway-awg3.service",
            ROOT / "deploy" / "repair-awg3-runtime.sh",
        )
    )
    assert "/opt/sg-gateway/awg3" in corpus
    assert "sg-gateway-awg3.service" in corpus
    assert "/etc/amnezia/amneziawg/awg3.conf" in corpus
