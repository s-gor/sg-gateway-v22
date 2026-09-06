from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / "build-run.sh"


def test_02208_package_contract_uses_page_owned_clients_assets() -> None:
    text = BUILD.read_text(encoding="utf-8")
    old_collapse = "grep -Fq 'SG_DEVICE_COLLAPSE_V4_LAST_CSS' \"$root/app/web/templates/base.html\" || fail \"Нет финального Device Collapse V4\""
    old_cleanup = "grep -Fq 'SG_DEVICE_EXPANDED_CLEANUP_V1_LAST_CSS' \"$root/app/web/templates/base.html\" || fail \"Нет очистки раскрытой карточки устройства\""
    assert old_collapse not in text
    assert old_cleanup not in text
    assert "! grep -Fq 'SG_DEVICE_COLLAPSE_V4_LAST_CSS' \"$root/app/web/templates/base.html\"" in text
    assert "! grep -Fq 'SG_DEVICE_EXPANDED_CLEANUP_V1_LAST_CSS' \"$root/app/web/templates/base.html\"" in text
    for template in ("clients.html", "client_detail.html"):
        target = f'"$root/app/web/templates/{template}"'
        assert f'grep -Fq "static_asset(\'sg-device-collapse-v4.css\')" {target}' in text
        assert f'grep -Fq "static_asset(\'sg-device-expanded-cleanup-v1.css\')" {target}' in text
