from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
UNINSTALLER = ROOT / "deploy" / "full-uninstall-ubuntu.sh"
WORKFLOW = ROOT / ".github" / "workflows" / "reinstall-after-full-uninstall-smoke.yml"

CANONICAL_REINSTALL_COMMAND = (
    "curl -fsSL "
    "https://raw.githubusercontent.com/s-gor/sg-gateway-v22/dev-02206/"
    "deploy/install-from-github.sh | sudo env "
    "SG_GATEWAY_ALLOW_DEVELOPMENT=1 "
    "SG_GATEWAY_GITHUB_BRANCH=dev-02206 bash"
)


def test_full_uninstall_prints_the_canonical_reinstall_command():
    body = UNINSTALLER.read_text(encoding="utf-8")

    assert "Для повторной установки SG-Gateway выполните:" in body
    assert CANONICAL_REINSTALL_COMMAND in body
    assert "EXPECTED_SHA=" not in body


def test_reinstall_smoke_covers_the_real_same_server_lifecycle():
    body = WORKFLOW.read_text(encoding="utf-8")

    required_steps = (
        "Run first native install",
        "Run official full uninstall",
        "Verify deterministic post-uninstall state",
        "Reinstall on the same Ubuntu server",
        "Create and apply first AWG3 client after reinstall",
        "Verify second installation and both userspace profiles",
    )
    for step in required_steps:
        assert step in body

    assert "sudo test ! -e /opt/sg-gateway" in body
    assert "sudo test ! -e /etc/sg-gateway" in body
    assert "sudo test ! -e /var/lib/sg-gateway" in body
    assert 'show awg3 listen-port)' in body
    assert 'show awg31 listen-port)' in body
