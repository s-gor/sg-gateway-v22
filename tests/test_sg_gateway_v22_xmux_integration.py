from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def test_production_registers_xmux_without_old_backup_extension() -> None:
    body = (ROOT / 'app/production.py').read_text(encoding='utf-8')
    assert 'from app.xray.xmux_http import register_xmux_http' in body
    assert 'register_xmux_http(app)' in body
    assert 'full_backup_verify_http' not in body

def test_xmux_block_stays_awg_agnostic_while_exports_support_awg3() -> None:
    paths = [
        ROOT / 'app/xray/xmux.py',
        ROOT / 'app/xray/xmux_http.py',
        ROOT / 'app/web/templates/_xray_xmux_settings.html',
        ROOT / 'app/web/static/sg-xmux-settings-v1.js',
    ]
    joined = '\n'.join(p.read_text(encoding='utf-8').lower() for p in paths)
    assert 'amneziawg3' not in joined
    assert 'awg3' not in joined
    exports = (ROOT / 'app/clients/exports.py').read_text(encoding='utf-8')
    assert 'def build_awg3_config' in exports

def test_connections_uses_source_native_xmux_assets() -> None:
    body = (ROOT / 'app/web/templates/connections.html').read_text(encoding='utf-8')
    assert body.count('sg-xmux-settings-v1.css') == 1
    assert body.count('include "_xray_xmux_settings.html"') == 1
    assert body.count('sg-xmux-settings-v1.js') == 1
