from pathlib import Path
import sys

root = Path(sys.argv[1]).resolve()
path = root / "tests/test_preview27_layout_and_vision.py"
text = path.read_text(encoding="utf-8")
old = '''    assert "XTLS VISION" in template
    assert "{{ profile.flow }}" in template
    assert "Обязательный XTLS Vision для выбранного VLESS-профиля" in template
    assert "VLESS Encryption" in template
'''
new = '''    assert "XTLS VISION" in template
    assert "{{ profile.flow }}" in template
    assert "Vision · {{ profile.flow }}" in template
    assert "VLESS Encryption ·" in template
    assert "Обязательный XTLS Vision для выбранного VLESS-профиля" not in template
'''
if text.count(old) != 1:
    raise SystemExit(f"Preview27 Vision anchor count={text.count(old)}")
path.write_text(text.replace(old, new, 1), encoding="utf-8")
print("Preview27 Vision assertion aligned with compact metadata")
