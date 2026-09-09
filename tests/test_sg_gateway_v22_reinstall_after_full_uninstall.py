from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
NAIVE_SERVICE = ROOT / "deploy" / "sg-gateway-naiveproxy.service"
UNINSTALLER = ROOT / "deploy" / "full-uninstall-ubuntu.sh"
WORKFLOW = ROOT / ".github" / "workflows" / "reinstall-after-full-uninstall-smoke.yml"

CANONICAL_REINSTALL_COMMAND = (
    "curl -4 -fsSL "
    "https://raw.githubusercontent.com/s-gor/sg-gateway-v22/stable-02208/"
    "deploy/install-from-github.sh | sudo env "
    "SG_GATEWAY_GITHUB_BRANCH=stable-02208 bash"
)


def test_full_uninstall_prints_the_canonical_reinstall_command():
    body = UNINSTALLER.read_text(encoding="utf-8")

    assert "Для повторной установки SG-Gateway выполните:" in body
    assert CANONICAL_REINSTALL_COMMAND in body
    assert "SG_GATEWAY_SOURCE_COMMIT=" not in CANONICAL_REINSTALL_COMMAND
    assert "EXPECTED_SHA=" not in body


def test_reinstall_smoke_covers_the_real_same_server_lifecycle():
    body = WORKFLOW.read_text(encoding="utf-8")
    naive_service = NAIVE_SERVICE.read_text(encoding="utf-8")

    required_steps = (
        "Run first native install",
        "Verify first installation and AWG retirement",
        "Run official full uninstall",
        "Verify deterministic post-uninstall state",
        "Reinstall on the same Ubuntu server",
        "Verify second installation and current AWG profile",
    )
    for step in required_steps:
        assert step in body

    assert "sudo test ! -e /opt/sg-gateway" in body
    assert "sudo test ! -e /etc/sg-gateway" in body
    assert "sudo test ! -e /var/lib/sg-gateway" in body

    # AWG2/AWG3 are retired product runtimes. A clean install and a reinstall
    # must not expose them, while the independent AWG3.1 profile remains live.
    assert "! sudo systemctl is-active --quiet sg-gateway-awg.service" in body
    assert "! sudo systemctl is-active --quiet sg-gateway-awg3.service" in body
    assert "sudo systemctl is-active --quiet sg-gateway-awg31.service" in body
    assert "sudo test ! -e /etc/amnezia/amneziawg/awg0.conf" in body
    assert "sudo test ! -e /etc/amnezia/amneziawg/awg3.conf" in body
    assert 'show awg31 listen-port)' in body
    assert 'show awg3 listen-port)' not in body

    assert 'assert "amneziawg" not in access' in body
    assert 'assert "amneziawg3" not in access' in body
    assert 'assert "amneziawg31" in access' in body
    assert 'WHERE engine IN (\\"amneziawg\\",\\"amneziawg3\\")' in body

    # /var/lib/sg-gateway deliberately remains 0750 sg-gateway:sg-gateway.
    # NaiveProxy is isolated under its own primary account, so systemd must
    # grant that process the SG group solely for traversing the shared parent.
    assert "User=sg-naiveproxy" in naive_service
    assert "Group=sg-naiveproxy" in naive_service
    assert "SupplementaryGroups=sg-gateway" in naive_service
