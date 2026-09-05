from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
NEW = ROOT / "app/web/static/sg-ui-connections-components-v22-08.css"
OLD = ROOT / "app/web/static/sg-connections-visual-v1.css"

def test_02208_connections_visuals_live_in_named_component_layer():
    assert NEW.is_file()
    assert not OLD.exists()
    css = NEW.read_text(encoding="utf-8")
    for marker in (".cnv1-kicker", ".cnv1-engine-status", ".cnv1-engine-logo", ".cnv1-port-chip", ".cnv1-advanced", ".cnv1-note-panel"):
        assert marker in css

def test_02208_connections_component_layer_does_not_own_page_geometry():
    css = NEW.read_text(encoding="utf-8")
    for selector in ("cnv1-page", "cnv1-heading", "cnv1-heading-actions", "cnv1-engines", "cnv1-engine-wide"):
        assert re.search(rf"(?m)^\s*\.{selector}\s*\{{", css) is None, selector
