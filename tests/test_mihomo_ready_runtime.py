from pathlib import Path


def test_clean_installer_keeps_mihomo_ready():
    text = Path("install.sh").read_text(encoding="utf-8")
    assert "Mihomo runtime: clean install idle configuration ready" in text
    assert "systemctl enable --now mihomo.service" in text
    assert "systemctl disable sg-gateway-awg.service sg-gateway-singbox.service mihomo.service" not in text
    assert "listeners: []" in text
    assert "/usr/local/bin/mihomo -t -f /etc/mihomo/config.yaml" in text


def test_zero_client_apply_keeps_mihomo_active():
    text = Path("hostd/sg_hostd/client_runtime.py").read_text(encoding="utf-8")
    marker = 'def _apply_mihomo() -> EngineResult:'
    block = text.split(marker, 1)[1].split('def _singbox_binary()', 1)[0]
    assert '["systemctl", "stop", "mihomo.service"]' not in block
    assert '["systemctl", "enable", "mihomo.service"]' in block
    assert '["systemctl", "restart", "mihomo.service"]' in block
    assert '"Mihomo runtime готов; активных клиентов нет"' in block


def test_health_treats_idle_mihomo_as_ready_not_unused():
    text = Path("app/mihomo/service.py").read_text(encoding="utf-8")
    block = text.split('def health_status()', 1)[1].split('def build_device_yaml', 1)[0]
    assert "Не используется: служба Mihomo выключена" not in block
    assert "runtime готов; активных клиентов нет" in block
