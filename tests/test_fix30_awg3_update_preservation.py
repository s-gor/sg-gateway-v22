from pathlib import Path


def test_panel_update_preserves_awg3_userspace_and_checks_service_state():
    text = Path("deploy/update-from-github.sh").read_text(encoding="utf-8")
    assert "sg-gateway-awg3.service" in text
    assert '".venv"|"awg3") continue ;;' in text
    assert '"assets") continue ;;' in text
    assert "verify_runtime_states_unchanged" in text

