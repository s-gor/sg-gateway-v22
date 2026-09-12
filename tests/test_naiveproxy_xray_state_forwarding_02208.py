from pathlib import Path


SOURCE = Path("app/naiveproxy/integration.py")


def test_naiveproxy_protocol_ready_preserves_xray_state_keyword() -> None:
    text = SOURCE.read_text(encoding="utf-8")
    assert "def protocol_ready(client, kind: str, device=None, *, xray_state=None) -> bool:" in text
    assert "return original_protocol_ready(client, kind, device, xray_state=xray_state)" in text
