from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _block(body: str, name: str, next_name: str) -> str:
    start = body.index(f"{name}() {{")
    end = body.index(f"\n{next_name}() {{", start)
    return body[start:end]


def test_clean_install_never_auto_registers_warp() -> None:
    body = (ROOT / "install.sh").read_text(encoding="utf-8")
    assert "stage9_ensure_warp()" in body
    assert "[Engine 6/6] WARP wgcf-cli" in body
    final_stage = _block(body, "run_final_stage", "verify_client_identities_after_update")
    assert "stage9_ensure_warp" not in final_stage
    main = body[body.index("main() {"):]
    assert "Создание и активация WARP" not in main
    assert "stage9_ensure_warp" not in main
    assert "WARP:         создан и активен" not in body
    assert "helper установлен; создаётся при необходимости в Outbounds" in body
    assert "существующий профиль сохранён" in body


def test_manual_warp_creation_remains_available_after_install() -> None:
    outbounds = (ROOT / "app/web/templates/outbounds.html").read_text(encoding="utf-8")
    commands = (ROOT / "hostd/sg_hostd/commands.py").read_text(encoding="utf-8")
    assert "Создать WARP" in outbounds
    assert "warp.install" in commands


def test_optional_warp_fix_preserves_awg2_xmux_and_isolates_awg3() -> None:
    installer = (ROOT / "install.sh").read_text(encoding="utf-8").lower()
    assert 'amneziawg_tools_version="1.0.20260618-2"' in installer
    assert 'amneziawg_kmod_version="1.0.20260329-2"' in installer
    assert 'awg3_tools_version="3.0.20260805"' in installer
    assert 'prefix="$prefix/awg3" install' in installer
    assert "amneziawg-linux-kernel-module-3.0" not in installer
    assert (ROOT / "app/xray/xmux.py").is_file()
