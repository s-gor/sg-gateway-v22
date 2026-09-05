from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
VISUAL = ROOT / "app/web/static/sg-connections-visual-v1.css"

DEAD_CNV1_CLASSES = {
    "cnv1-engine-metrics",
    "cnv1-field-wide",
    "cnv1-form-section-title",
    "cnv1-key-grid",
    "cnv1-map",
    "cnv1-map-awg",
    "cnv1-map-branch",
    "cnv1-map-icon",
    "cnv1-map-internet",
    "cnv1-map-node",
    "cnv1-map-node-head",
    "cnv1-map-panel",
    "cnv1-map-status",
    "cnv1-map-targets",
    "cnv1-map-xray",
    "cnv1-page-footer",
    "cnv1-panel-head",
    "cnv1-summary",
    "cnv1-summary-card",
    "cnv1-summary-icon",
    "cnv1-summary-label",
    "cnv1-summary-note",
    "cnv1-summary-ports",
    "cnv1-summary-value",
}


def test_02208_connections_visual_css_does_not_keep_dead_template_namespaces():
    css = VISUAL.read_text(encoding="utf-8")
    for class_name in sorted(DEAD_CNV1_CLASSES):
        assert f".{class_name}" not in css, class_name
