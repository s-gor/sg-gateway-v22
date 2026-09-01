from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INSTALL_WRAPPER = ROOT / "deploy" / "install-from-github.sh"
UPDATE_WRAPPER = ROOT / "deploy" / "update-from-github.sh"
UNINSTALL_WRAPPER = ROOT / "deploy" / "uninstall-from-github.sh"
COMMANDS = ROOT / "deploy" / "GITHUB-COMMANDS.md"
INSTALL_SOURCE_COMMIT = "2e96ea97992509f8ff2fdce8b8d23aa0dc5a1dff"

INSTALL_URL = (
    "https://raw.githubusercontent.com/s-gor/sg-gateway-v22/"
    f"{INSTALL_SOURCE_COMMIT}/deploy/install-from-github.sh"
)
UPDATE_COMMAND = (
    "curl -4 -fsSL "
    "https://raw.githubusercontent.com/s-gor/sg-gateway-v22/stable-02206/"
    "deploy/update-from-github.sh | sudo env "
    "SG_GATEWAY_GITHUB_BRANCH=stable-02206 bash"
)
UNINSTALL_COMMAND = (
    "curl -4 -fsSL "
    "https://raw.githubusercontent.com/s-gor/sg-gateway-v22/stable-02206/"
    "deploy/uninstall-from-github.sh | sudo env "
    "SG_GATEWAY_GITHUB_BRANCH=stable-02206 bash"
)


def test_public_github_commands_are_published():
    body = COMMANDS.read_text(encoding="utf-8")
    assert INSTALL_URL in body
    assert "SG_GATEWAY_GITHUB_BRANCH=stable-02206" in body
    assert f"SG_GATEWAY_SOURCE_COMMIT={INSTALL_SOURCE_COMMIT}" in body
    assert UPDATE_COMMAND in body
    assert UNINSTALL_COMMAND in body


def test_public_uninstall_wrapper_is_pinned_and_delegates_to_official_uninstaller():
    body = UNINSTALL_WRAPPER.read_text(encoding="utf-8")
    assert 'REPOSITORY="s-gor/sg-gateway-v22"' in body
    assert 'stable-02206' in body
    assert 'SG_GATEWAY_ALLOW_DEVELOPMENT' not in body
    assert 'stable uninstaller is pinned to stable-02206' in body
    assert 'archive/refs/heads/${BRANCH}.tar.gz' in body
    assert 'gzip -t "$ARCHIVE"' in body
    assert 'tar -xzf "$ARCHIVE"' in body
    assert 'deploy/full-uninstall-ubuntu.sh' in body
    assert 'bash "$UNINSTALLER"' in body
    assert 'DELETE SG-GATEWAY' not in body


def test_public_install_and_update_default_to_stable_channel():
    install = INSTALL_WRAPPER.read_text(encoding="utf-8")
    update = UPDATE_WRAPPER.read_text(encoding="utf-8")
    assert 'SG_GATEWAY_ALLOW_DEVELOPMENT' not in install
    assert 'stable installer is pinned to stable-02206' in install
    assert '${SG_GATEWAY_UPDATE_BRANCH:-stable-02206}' in install
    assert '${SG_GATEWAY_UPDATE_BRANCH:-stable-02206}' in update
