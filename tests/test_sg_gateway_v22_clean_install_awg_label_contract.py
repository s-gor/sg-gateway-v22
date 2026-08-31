from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INSTALL_SOURCE_COMMIT = "e7cd63deab9c3a34b6aee910c61017ff8a8b9c6e"


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_public_clean_install_commands_pin_verified_source_commit() -> None:
    expected_url = (
        "https://raw.githubusercontent.com/s-gor/sg-gateway-v22/"
        f"{INSTALL_SOURCE_COMMIT}/deploy/install-from-github.sh"
    )
    expected_source = f"SG_GATEWAY_SOURCE_COMMIT={INSTALL_SOURCE_COMMIT}"

    for path in ("deploy/GITHUB-COMMANDS.md", "PUBLICATION-02206.md"):
        text = _read(path)
        assert expected_url in text, path
        assert "SG_GATEWAY_GITHUB_BRANCH=stable-02206" in text, path
        assert expected_source in text, path


def test_clean_install_smoke_verifies_seeded_awg_subscription_labels() -> None:
    workflow = _read(".github/workflows/clean-install-awg3-smoke.yml")

    assert "Verify clean-install subscription labels" in workflow
    assert "from app.clients.sg_subscription import build_sg_subscription_text" in workflow
    assert '"amneziawg", "amneziawg3", "amneziawg31"' in workflow
    assert 'assert labels == ["sg-admin"] * 3' in workflow
    assert 'assert "sg-admin · Устройство" not in labels' in workflow
