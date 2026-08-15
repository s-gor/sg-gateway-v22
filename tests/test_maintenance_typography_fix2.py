from pathlib import Path

def test_maintenance_typography_fix2():
    root = Path(__file__).resolve().parents[1]
    css = (root / 'app/web/static/sg-maintenance-typography-fix2.css').read_text(encoding='utf-8')
    assert '.mtv2-health-issues small' in css
    assert 'font-size: 11.2px' in css
    assert '.mtv2-diagnostics-grid span' in css
    assert '.mtv2-operation-list p' in css
    assert css.count('{') == css.count('}')
