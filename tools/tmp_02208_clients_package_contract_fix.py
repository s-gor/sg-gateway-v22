from __future__ import annotations

from pathlib import Path


def write_test() -> None:
    Path("tests/test_sg_gateway_v22_clients_package_contract_02208.py").write_text(
        r'''from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / "build-run.sh"


def test_02208_package_contract_uses_page_owned_clients_assets() -> None:
    text = BUILD.read_text(encoding="utf-8")
    assert "SG_DEVICE_COLLAPSE_V4_LAST_CSS" not in text
    assert "SG_DEVICE_EXPANDED_CLEANUP_V1_LAST_CSS" not in text
    for template in ("clients.html", "client_detail.html"):
        target = f'"$root/app/web/templates/{template}"'
        assert f'grep -Fq "static_asset(\'sg-device-collapse-v4.css\')" {target}' in text
        assert f'grep -Fq "static_asset(\'sg-device-expanded-cleanup-v1.css\')" {target}' in text
''',
        encoding="utf-8",
    )


def migrate_build_run() -> None:
    path = Path("build-run.sh")
    text = path.read_text(encoding="utf-8")
    old = '''  grep -Fq 'SG_DEVICE_COLLAPSE_V4_LAST_CSS' "$root/app/web/templates/base.html" || fail "Нет финального Device Collapse V4"\n  grep -Fq 'SG_DEVICE_EXPANDED_CLEANUP_V1_LAST_CSS' "$root/app/web/templates/base.html" || fail "Нет очистки раскрытой карточки устройства"\n'''
    new = '''  ! grep -Fq 'SG_DEVICE_COLLAPSE_V4_LAST_CSS' "$root/app/web/templates/base.html" || fail "Legacy Device Collapse V4 всё ещё загружается из base.html"\n  ! grep -Fq 'SG_DEVICE_EXPANDED_CLEANUP_V1_LAST_CSS' "$root/app/web/templates/base.html" || fail "Legacy Device Expanded Cleanup всё ещё загружается из base.html"\n  grep -Fq "static_asset('sg-device-collapse-v4.css')" "$root/app/web/templates/clients.html" || fail "Clients не владеет Device Collapse V4 через static_asset"\n  grep -Fq "static_asset('sg-device-expanded-cleanup-v1.css')" "$root/app/web/templates/clients.html" || fail "Clients не владеет Device Expanded Cleanup через static_asset"\n  grep -Fq "static_asset('sg-device-collapse-v4.css')" "$root/app/web/templates/client_detail.html" || fail "Client Detail не владеет Device Collapse V4 через static_asset"\n  grep -Fq "static_asset('sg-device-expanded-cleanup-v1.css')" "$root/app/web/templates/client_detail.html" || fail "Client Detail не владеет Device Expanded Cleanup через static_asset"\n'''
    if old not in text:
        raise RuntimeError("legacy package Device Collapse contract not found")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


if __name__ == "__main__":
    write_test()
    migrate_build_run()
