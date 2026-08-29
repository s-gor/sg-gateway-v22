from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
UNINSTALLER = ROOT / "deploy" / "full-uninstall-ubuntu.sh"
WORKFLOW = ROOT / ".github" / "workflows" / "reinstall-after-full-uninstall-smoke.yml"

CANONICAL_REINSTALL_COMMAND = (
    "curl -4 -fsSL "
    "https://raw.githubusercontent.com/s-gor/sg-gateway-v22/stable-02206/"
    "deploy/install-from-github.sh | sudo env "
    "SG_GATEWAY_GITHUB_BRANCH=stable-02206 bash"
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
        "Verify seeded sg-admin complete profile set after reinstall",
        "Create and apply additional AWG3 client after reinstall",
        "Verify second installation and both userspace profiles",
    )
    for step in required_steps:
        assert step in body

    assert "sudo test ! -e /opt/sg-gateway" in body
    assert "sudo test ! -e /etc/sg-gateway" in body
    assert "sudo test ! -e /var/lib/sg-gateway" in body
    assert "assert int(peers) == 1" in body
    assert "assert int(seeded) == 1" in body
    assert "sudo test ! -e /var/lib/sg-gateway/.seeded-admin-awg3.pending" in body
    for access in (
        "xray_reality_tcp",
        "xray_xhttp_reality",
        "amneziawg",
        "amneziawg3",
        "amneziawg31",
        "mihomo",
        "sgclient",
    ):
        assert f'"{access}"' in body
    assert "assert actual_access == expected_access" in body
    assert 'show awg3 listen-port)' in body
    assert 'show awg31 listen-port)' in body
