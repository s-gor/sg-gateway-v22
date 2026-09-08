from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "app/web/templates/base.html"
PERF = ROOT / "app/web/static/sg-ui-performance-v22-08.css"


def test_base_loads_final_performance_layer_after_ui_components():
    text = BASE.read_text(encoding="utf-8")
    components = "sg-ui-components-v22-08.css"
    performance = "sg-ui-performance-v22-08.css"

    assert performance in text
    assert text.index(performance) > text.index(components)


def test_obsolete_preview_layers_are_not_loaded_globally():
    text = BASE.read_text(encoding="utf-8")

    assert "sg-preview28-final.css" not in text
    assert "sg-preview32-final.css" not in text
    assert "sg-preview34-final.css" not in text
    assert "sg-preview45-xray-theme-fix.css" not in text


def test_performance_layer_disables_fixed_full_page_background_paint():
    text = PERF.read_text(encoding="utf-8")

    assert "background-attachment: scroll !important" in text
    assert "contain: paint" in text
