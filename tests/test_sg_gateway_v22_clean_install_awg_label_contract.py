from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_public_clean_install_commands_pin_one_verified_02208_source_commit() -> None:
    commands = _read("deploy/GITHUB-COMMANDS.md")
    publication = _read("PUBLICATION-02208.md")
    readme = _read("README.md")
    match = re.search(
        r"https://raw\.githubusercontent\.com/s-gor/sg-gateway-v22/([0-9a-f]{40})/deploy/install-from-github\.sh",
        commands,
    )
    assert match is not None
    commit = match.group(1)
    expected_url = f"https://raw.githubusercontent.com/s-gor/sg-gateway-v22/{commit}/deploy/install-from-github.sh"
    expected_source = f"SG_GATEWAY_SOURCE_COMMIT={commit}"
    for text in (commands, publication, readme):
        assert expected_url in text
        assert "SG_GATEWAY_GITHUB_BRANCH=stable-02208" in text
        assert expected_source in text


def test_clean_install_smoke_verifies_seeded_awg_subscription_labels() -> None:
    workflow = _read(".github/workflows/clean-install-awg3-smoke.yml")
    assert "Verify clean-install subscription labels" in workflow
    assert "from app.clients.sg_subscription import build_sg_subscription_text" in workflow
    assert '"amneziawg", "amneziawg3", "amneziawg31"' in workflow
    assert 'assert labels == ["sg-admin"] * 3' in workflow
    assert 'assert "sg-admin · Устройство" not in labels' in workflow
