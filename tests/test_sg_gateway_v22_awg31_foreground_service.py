from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_awg31_simple_service_tracks_foreground_daemon() -> None:
    unit = (ROOT / "deploy/sg-gateway-awg31.service").read_text(encoding="utf-8")
    launcher = (ROOT / "deploy/sg-gateway-awg31-userspace.sh").read_text(encoding="utf-8")

    assert "Type=simple" in unit
    assert '"$RUNTIME/bin/amneziawg-go" --foreground "$IFACE" &' in launcher
    assert 'wait "$PID"' in launcher
