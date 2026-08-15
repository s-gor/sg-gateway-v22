from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
CSS = (ROOT / "app/web/static/sg-luxury-jade-depth-v2.css").read_text(encoding="utf-8")
TEMPLATES = "\n".join(p.read_text(encoding="utf-8") for p in (ROOT / "app/web/templates").glob("*.html"))

APPROVED = {
"#E5ECE7","#DCE5E0","#F8F5EE","#FBFAF6","#DDDAD2","#EFE5D5","#456F5C","#356B56","#B88A45","#29312C","#66716A","#89968A","#68786C",
"#F1F3EF","#DCE4DD","#E8EFF2","#D8E1E4","#FEFCF7","#F2ECE1","#F1EADE","#E1D8CA","#F8F0E4","#E8D9C3","#FFFDFC","#F6F1E7","#F6F0E6","#E7DCCB","#739E88","#4E7965","#709A84","#4D7864","#7EAA93","#5B866F","#4F7764","#3E6050","#FBF4E8","#F1EEE6","#2B342E","#55FFFFFF"
}

def test_only_approved_hex_colours():
    found={x.upper() for x in re.findall(r"#[0-9A-Fa-f]{6,8}", CSS)}
    assert found <= APPROVED, sorted(found-APPROVED)

def test_exact_gradients_and_background():
    for value in (
      "linear-gradient(180deg, #F1F3EF 0%, #DCE4DD 100%)",
      "linear-gradient(180deg, #E8EFF2 0%, #D8E1E4 100%)",
      "linear-gradient(180deg, #FEFCF7 0%, #F2ECE1 100%)",
      "linear-gradient(180deg, #F1EADE 0%, #E1D8CA 100%)",
      "linear-gradient(180deg, #F8F0E4 0%, #E8D9C3 100%)",
      "linear-gradient(180deg, #FFFDFC 0%, #F6F1E7 100%)",
      "linear-gradient(180deg, #F6F0E6 0%, #E7DCCB 100%)",
      "linear-gradient(180deg, #739E88 0%, #4E7965 100%)",
      "linear-gradient(180deg, #709A84 0%, #4D7864 100%)",
      "linear-gradient(180deg, #7EAA93 0%, #5B866F 100%)",
      "linear-gradient(180deg, #4F7764 0%, #3E6050 100%)",
      "radial-gradient(ellipse 68% 68% at 78% -8%, #FBF4E8 0%, #F1EEE6 22%, #E5ECE7 58%, #E5ECE7 100%)",
    ): assert value in CSS

def test_exact_depth_and_rim():
    assert "0 2px 12px rgba(43, 52, 46, .20)" in CSS
    assert "0 4px 18px rgba(43, 52, 46, .17)" in CSS
    assert "inset 0 1px 0 rgba(255, 255, 255, .333)" in CSS
    assert "inset 1px 0 0 rgba(255, 255, 255, .333)" in CSS
    assert "inset -1px 0 0 rgba(255, 255, 255, .333)" in CSS
    assert "inset 0 -1px" not in CSS

def test_semantic_roles_are_in_templates():
    for role in ("sg-ljd-card-large","sg-ljd-card","sg-ljd-nested","sg-ljd-raised","sg-ljd-strip","sg-ljd-tile-grid","sg-ljd-table","sg-ljd-key-action"):
        assert role in TEMPLATES, role

def test_dark_theme_is_not_targeted():
    without_comments = re.sub(r"/\*.*?\*/", "", CSS, flags=re.S)
    for block in without_comments.split("}"):
        if "{" not in block: continue
        selector=block.split("{",1)[0].strip()
        if selector.startswith("@") or selector.startswith(":root"): continue
        assert 'html[data-theme="light"]' in selector, selector

def test_not_a_generic_card_recolour_layer():
    assert 'html[data-theme="light"] .status-card' not in CSS
    assert 'html[data-theme="light"] :is(' not in CSS
    assert '.sg-ljd-card' in CSS

def test_old_light_layers_are_not_loaded():
    base=(ROOT / 'app/web/templates/base.html').read_text(encoding='utf-8')
    assert 'sg-light-latte-graphite-v1.css' not in base
    assert 'sg-light-theme-polish-fix2.css' not in base
    assert 'sg-luxury-jade-depth-v2.css' in base
