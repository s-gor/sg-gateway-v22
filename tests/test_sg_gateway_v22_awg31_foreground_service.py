from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_awg31_simple_service_tracks_foreground_daemon() -> None:
    unit = (ROOT / "deploy/sg-gateway-awg31.service").read_text(encoding="utf-8")
    launcher = (ROOT / "deploy/sg-gateway-awg31-userspace.sh").read_text(encoding="utf-8")

    assert "Type=simple" in unit
    assert 'AWG_GO="$RUNTIME/bin/amneziawg-go"' in launcher
    assert '"$AWG_GO" --foreground "$IFACE" &' in launcher
    assert "PID=$!" in launcher
    assert 'wait "$PID"' in launcher
