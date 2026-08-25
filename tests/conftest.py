from __future__ import annotations

import subprocess
from pathlib import Path

import pytest


@pytest.fixture(scope="session", autouse=True)
def name_detached_ci_checkout() -> None:
    """Give file:// clone tests a resolvable branch in detached PR checkouts."""

    root = Path(__file__).resolve().parents[1]
    branch = subprocess.check_output(
        ["git", "branch", "--show-current"], cwd=root, text=True
    ).strip()
    if not branch:
        subprocess.run(
            ["git", "switch", "-c", "ci-test-head"],
            cwd=root,
            text=True,
            capture_output=True,
            check=True,
        )


@pytest.fixture(autouse=True)
def isolate_sg_gateway_runtime_paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep tests away from privileged production paths such as /var/lib."""

    from app.mihomo import service as mihomo_service

    runtime_root = tmp_path / ".sg-gateway-test-runtime"
    candidate_dir = runtime_root / "candidates" / "mihomo"
    state_dir = runtime_root / "mihomo"

    monkeypatch.setattr(mihomo_service, "MIHOMO_CANDIDATE_DIR", candidate_dir)
    monkeypatch.setattr(
        mihomo_service,
        "MIHOMO_CANDIDATE",
        candidate_dir / "candidate.yaml",
    )
    monkeypatch.setattr(
        mihomo_service,
        "MIHOMO_CANDIDATE_META",
        candidate_dir / "candidate.json",
    )
    monkeypatch.setattr(mihomo_service, "MIHOMO_STATE_DIR", state_dir)
    monkeypatch.setattr(
        mihomo_service,
        "MIHOMO_BACKUP_DIR",
        state_dir / "backups",
    )
