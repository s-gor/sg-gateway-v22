from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _helper_text() -> str:
    return (ROOT / "app" / "mihomo" / "helper.py").read_text(
        encoding="utf-8"
    )


def _apply_body(helper: str) -> str:
    start = helper.index("def apply_candidate(")
    end = helper.index("\ndef ", start + 1)
    return helper[start:end]


def test_mihomo_listener_readiness_is_not_a_transaction_gate():
    helper = _helper_text()
    assert "def _verify_listeners" not in helper
    assert "_verify_listeners(meta)" not in helper


def test_mihomo_apply_checks_service_without_listener_transaction():
    apply_body = _apply_body(_helper_text())
    active = (
        '_run(["systemctl", "is-active", "--quiet", '
        '"mihomo.service"])'
    )
    assert active in apply_body
    assert "_verify_listeners" not in apply_body
