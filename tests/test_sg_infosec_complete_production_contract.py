from pathlib import Path


def test_production_registers_complete_infosec_stack_in_safe_order() -> None:
    text = Path("app/production.py").read_text(encoding="utf-8")

    required = [
        "register_sg_infosec(app)",
        "register_hardened_sg_infosec_guard(app)",
        "register_sg_infosec_management(app)",
        "register_sg_infosec_guard_management(app)",
    ]
    for item in required:
        assert item in text

    positions = [text.index(item) for item in required]
    assert positions == sorted(positions)
    assert "from app.security.sg_infosec_guard_runtime import" in text
    assert "register_sg_infosec_guard(app)" not in text
