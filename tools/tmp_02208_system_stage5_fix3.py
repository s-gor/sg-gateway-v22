from pathlib import Path


def rewrite_simple_dials_contract() -> None:
    path = Path("tests/test_system_simple_dials_v1.py")
    text = path.read_text(encoding="utf-8")
    old = '''    base = (ROOT / "app/web/templates/base.html").read_text(encoding="utf-8")\n    css = (ROOT / "app/web/static/sg-system-simple-dials-v1.css").read_text(encoding="utf-8")\n\n    assert "sg-system-simple-dials-v1.css" in base\n    assert "sg-system-dial-sg-gateway-sector-v1.css" not in base\n    assert "sg-system-dial-sg-gateway-sector-v1.js" not in base\n    assert "sg-system-dial-math-sync-v1.js" not in base\n'''
    new = '''    base = (ROOT / "app/web/templates/base.html").read_text(encoding="utf-8")\n    system = (ROOT / "app/web/templates/system.html").read_text(encoding="utf-8")\n    css = (ROOT / "app/web/static/sg-system-simple-dials-v1.css").read_text(encoding="utf-8")\n\n    assert "static_asset('sg-system-simple-dials-v1.css')" in system\n    assert "sg-system-simple-dials-v1.css" not in base\n    assert "sg-system-dial-sg-gateway-sector-v1.css" not in base\n    assert "sg-system-dial-sg-gateway-sector-v1.js" not in base\n    assert "sg-system-dial-math-sync-v1.js" not in base\n'''
    if old not in text:
        raise RuntimeError("simple dials ownership contract marker missing")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")
