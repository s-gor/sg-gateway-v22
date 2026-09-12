from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EXPECTED_PRODUCTION_SOURCE = "6d8b07125289566a6e8a7ba206094d8969e92125"


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_public_clean_install_commands_pin_one_verified_02208_source_commit() -> None:
    commands = _read("deploy/GITHUB-COMMANDS.md")
    publication = _read("PUBLICATION-02208.md")
    readme = _read("README.md")
    uninstall_wrapper = _read("deploy/uninstall-from-github.sh")
    match = re.search(
        r"https://raw\.githubusercontent\.com/s-gor/sg-gateway-v22/([0-9a-f]{40})/deploy/install-from-github\.sh",
        commands,
    )
    assert match is not None
    commit = match.group(1)
    assert commit == EXPECTED_PRODUCTION_SOURCE
    expected_url = f"https://raw.githubusercontent.com/s-gor/sg-gateway-v22/{commit}/deploy/install-from-github.sh"
    expected_source = f"SG_GATEWAY_SOURCE_COMMIT={commit}"
    for text in (commands, publication, readme, uninstall_wrapper):
        assert expected_url in text
        assert "SG_GATEWAY_GITHUB_BRANCH=stable-02208" in text
        assert expected_source in text


def test_clean_install_smoke_verifies_only_current_awg_profile_for_sg_admin() -> None:
    workflow = _read(".github/workflows/clean-install-awg3-smoke.yml")

    assert "Verify sg-admin exposes only current AWG profile" in workflow
    assert 'assert "amneziawg" not in access' in workflow
    assert 'assert "amneziawg3" not in access' in workflow
    assert 'assert "amneziawg31" in access' in workflow
