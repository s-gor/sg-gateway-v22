from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_system_uses_only_simple_blue_neutral_dials():
    main = (ROOT / "app/main.py").read_text(encoding="utf-8")
    base = (ROOT / "app/web/templates/base.html").read_text(encoding="utf-8")
    system = (ROOT / "app/web/templates/system.html").read_text(encoding="utf-8")
    css = (ROOT / "app/web/static/sg-system-simple-dials-v1.css").read_text(encoding="utf-8")

    assert "static_asset('sg-system-simple-dials-v1.css')" in system
    assert "sg-system-simple-dials-v1.css" not in base
    assert "sg-system-dial-sg-gateway-sector-v1.css" not in base
    assert "sg-system-dial-sg-gateway-sector-v1.js" not in base
    assert "sg-system-dial-math-sync-v1.js" not in base

    assert "var(--sg-simple-dial-used)" in main
    assert "var(--sg-simple-dial-empty)" in main
    assert "gradient_parts.append" not in main
    assert '"free", "Доступно"' in main
    assert "free_partition" in main

    assert "--sg-simple-dial-used: #4F9BFF" in css
    assert "--sg-simple-dial-empty: #233D57" in css
    assert "--sg-simple-dial-empty: #D7E1DD" in css
    assert '[data-sg-cpu-card="1"] .sv1-cpu-dial' in css
    assert "--sg-dial-gateway-percent" not in css
