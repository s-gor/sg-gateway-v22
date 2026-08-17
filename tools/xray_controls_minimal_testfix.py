import sys
from pathlib import Path

ROOT = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path(__file__).resolve().parents[1]
path = ROOT / "tests/test_preview27_layout_and_vision.py"
text = path.read_text(encoding="utf-8")
old = '''def test_vision_is_explicit_in_connections_ui():\n    template = (ROOT / "app/web/templates/connections.html").read_text(encoding="utf-8")\n    assert "XTLS VISION" in template\n    assert "{{ profile.flow }}" in template\n    assert "Vision · {{ profile.flow }}" in template\n    assert "VLESS Encryption ·" in template\n    assert "Обязательный XTLS Vision для выбранного VLESS-профиля" not in template\n'''
new = '''def test_vision_contract_remains_explicit_without_duplicate_parameter_badges():\n    template = (ROOT / "app/web/templates/connections.html").read_text(encoding="utf-8")\n    profiles = (ROOT / "app/xray/profiles.py").read_text(encoding="utf-8")\n    assert "XTLS VISION" in template\n    assert '{{ profile.flow }}' not in template\n    assert "Vision · {{ profile.flow }}" not in template\n    assert "VLESS Encryption ·" not in template\n    assert 'REALITY_TCP_FLOW = "xtls-rprx-vision"' in profiles\n    assert "Обязательный XTLS Vision для выбранного VLESS-профиля" not in template\n'''
if old not in text:
    raise SystemExit("legacy Preview27 Vision UI test not found")
path.write_text(text.replace(old, new, 1), encoding="utf-8")
print("Preview27 Vision contract normalized for minimal Connections UI")
