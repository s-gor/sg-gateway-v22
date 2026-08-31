from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INSTALL_WRAPPER = ROOT / "deploy" / "install-from-github.sh"
UNINSTALL_WRAPPER = ROOT / "deploy" / "uninstall-from-github.sh"
COMMANDS = ROOT / "deploy" / "GITHUB-COMMANDS.md"

INSTALL_COMMAND = (
    "curl -4 -fsSL "
    "https://raw.githubusercontent.com/s-gor/sg-gateway-v22/dev-02206/"
    "deploy/install-from-github.sh | sudo env "
    "SG_GATEWAY_ALLOW_DEVELOPMENT=1 "
    "SG_GATEWAY_GITHUB_BRANCH=dev-02206 bash"
)
UNINSTALL_COMMAND = (
    "curl -4 -fsSL "
    "https://raw.githubusercontent.com/s-gor/sg-gateway-v22/dev-02206/"
    "deploy/uninstall-from-github.sh | sudo env "
    "SG_GATEWAY_ALLOW_DEVELOPMENT=1 "
    "SG_GATEWAY_GITHUB_BRANCH=dev-02206 bash"
)


def test_public_github_install_and_uninstall_commands_are_published():
    body = COMMANDS.read_text(encoding="utf-8")

    assert INSTALL_COMMAND in body
    assert UNINSTALL_COMMAND in body


def test_public_uninstall_wrapper_is_pinned_and_delegates_to_official_uninstaller():
    body = UNINSTALL_WRAPPER.read_text(encoding="utf-8")

    assert 'REPOSITORY="s-gor/sg-gateway-v22"' in body
    assert 'dev-02206' in body
    assert 'SG_GATEWAY_ALLOW_DEVELOPMENT' in body
    assert 'development uninstaller is pinned to dev-02206' in body
    assert 'archive/refs/heads/${BRANCH}.tar.gz' in body
    assert 'gzip -t "$ARCHIVE"' in body
    assert 'tar -xzf "$ARCHIVE"' in body
    assert 'deploy/full-uninstall-ubuntu.sh' in body
    assert 'bash "$UNINSTALLER"' in body
    assert 'DELETE SG-GATEWAY' not in body


def test_public_install_wrapper_remains_pinned_to_the_same_channel():
    body = INSTALL_WRAPPER.read_text(encoding="utf-8")

    assert 'SG_GATEWAY_ALLOW_DEVELOPMENT' in body
    assert 'development installer is pinned to dev-02206' in body
