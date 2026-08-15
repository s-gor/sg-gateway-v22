from pathlib import Path
from jinja2 import Environment


def test_routing_preview40_templates_and_styles():
    root = Path(__file__).resolve().parents[1]
    routing = (root / "app/web/templates/routing.html").read_text(encoding="utf-8")
    geofiles = (root / "app/web/templates/_geofiles_panel.html").read_text(encoding="utf-8")
    styles = (root / "app/web/static/sg-routing-client096.css").read_text(encoding="utf-8")
    Environment().parse(routing)
    Environment().parse(geofiles)
    assert "r096-tabs" in routing
    assert "r096-selected-card" in routing
    assert "r096-main-rules" in routing
    assert "r096-geo" in geofiles
    assert "--r096-accent" in styles
    assert "#0B121C" in styles
    assert "#E5ECE7" in styles
