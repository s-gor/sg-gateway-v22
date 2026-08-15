from pathlib import Path


def test_hysteria2_restart_wait_contract():
    text = Path("hostd/sg_hostd/client_runtime.py").read_text(encoding="utf-8")
    assert "import time\n" in text
    assert "deadline = time.monotonic() + 10.0" in text
    assert "while not _udp_port_listening(hysteria_profile.port):" in text
    assert "time.sleep(0.25)" in text
    assert "не слушается через 10 секунд после запуска Xray" in text
    assert "не слушается после запуска Xray" not in text
