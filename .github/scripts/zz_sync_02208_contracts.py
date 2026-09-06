from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    target = Path(path)
    text = target.read_text(encoding="utf-8")
    if text.count(old) != 1:
        raise SystemExit(f"expected one match in {path}: {old[:90]!r}")
    target.write_text(text.replace(old, new, 1), encoding="utf-8")


# NaiveProxy is intentionally before the final explanatory note.
replace_once(
    "tests/test_naiveproxy_http_02207.py",
    '    assert template.index("cnv1-note-panel") < template.index(\'_naiveproxy_panel.html\')\n',
    '    assert template.index(\'_naiveproxy_panel.html\') < template.index("cnv1-note-panel")\n',
)
replace_once(
    "tests/test_naiveproxy_http_02207.py",
    '    assert "data-naive-runtime" in panel\n',
    '    assert "data-naive-runtime" not in panel\n',
)
replace_once(
    "tests/test_naiveproxy_integration_02207.py",
    '    assert template.index("cnv1-note-panel") < template.index(\'_naiveproxy_panel.html\')\n',
    '    assert template.index(\'_naiveproxy_panel.html\') < template.index("cnv1-note-panel")\n',
)

# AWG header divider and NaiveProxy runtime row were explicitly removed from the UI.
replace_once(
    "tests/test_sg_gateway_v22_awg_cards_unified_ui.py",
    '    assert ".page-connections .awgd-shell > .cnv1-engine-head { border-bottom: 1px solid var(--sg-line-soft); }" in stylesheet\n',
    '    assert ".page-connections .awgd-shell > .cnv1-engine-head { border-bottom:" not in stylesheet\n',
)
replace_once(
    "tests/test_sg_gateway_v22_compact_protocol_cards_ui_02207.py",
    '    assert "data-naive-runtime" in naive\n',
    '    assert "data-naive-runtime" not in naive\n',
)
replace_once(
    "tests/test_sg_gateway_v22_compact_protocol_cards_ui_02207.py",
    '    assert connections.index("cnv1-note-panel") < connections.index(\'_naiveproxy_panel.html\')\n',
    '    assert connections.index(\'_naiveproxy_panel.html\') < connections.index("cnv1-note-panel")\n',
)

# Replace the obsolete byte-for-byte rollback contract with current semantic invariants.
restore_test = Path("tests/test_connections_restore_naiveproxy_bottom_02208.py")
restore_test.write_text(
    '''from pathlib import Path\n\nROOT = Path(__file__).resolve().parents[1]\n\n\ndef test_connections_uses_current_canonical_geometry_contract():\n    css = (ROOT / "app/web/static/sg-ui-connections-v22-08.css").read_text(encoding="utf-8")\n    template = (ROOT / "app/web/templates/connections.html").read_text(encoding="utf-8")\n    mihomo = (ROOT / "app/web/templates/_mihomo_panel.html").read_text(encoding="utf-8")\n\n    assert "calc(" not in css\n    assert "margin-inline" not in css\n    assert '<div class="awgd-inner-rail sg-ui-rail">' in template\n    assert '<div class="mhv2-inner-rail sg-ui-rail">' in mihomo\n\n\ndef test_connections_is_direct_template_not_wrapper():\n    template = (ROOT / "app/web/templates/connections.html").read_text(encoding="utf-8")\n\n    assert template.startswith('{% extends "base.html" %}')\n    assert 'connections_legacy_8f7481cb.html' not in template\n    assert 'class="cnv1-engine-pair sg-ui-grid"' in template\n    assert 'class="awgd-card awgd-card-v2"' in template\n    assert '{% include "_mihomo_panel.html" %}' in template\n    assert 'name="fingerprint"' in template\n\n\ndef test_naiveproxy_precedes_final_connections_note():\n    template = (ROOT / "app/web/templates/connections.html").read_text(encoding="utf-8")\n\n    naive = template.index('{% include "_naiveproxy_panel.html" %}')\n    note = template.index('class="cnv1-note-panel sg-ljd-card sg-ui-card"')\n    content_end = template.index('{% endblock %}', note)\n\n    assert naive < note < content_end\n    assert template.count('_naiveproxy_panel.html') == 1\n    assert 'sg-naiveproxy-bottom-v1.css' not in template\n    assert 'cnv1-layout-grid' not in template\n    assert 'cnv1-grid-cell' not in template\n\n\ndef test_restore_has_no_legacy_wrapper_artifacts():\n    assert not (ROOT / "app/web/templates/connections_legacy_8f7481cb.html").exists()\n    assert not (ROOT / "app/web/static/sg-naiveproxy-bottom-v1.css").exists()\n''',
    encoding="utf-8",
)

# Restore the installer startup identity contract inside the live 24-stage main().
replace_once(
    "install.sh",
    "  printf '\\\n%s[SG-Gateway]%s Запускаю полный мастер SG-Gateway 0.1.0-022.08 · 24 этапа\\\n' \"$CYAN\" \"$RESET\"\n",
    "  printf '\\\n%s[SG-Gateway]%s Запускаю полный мастер SG-Gateway 0.1.0-022.08 · 24 этапа\\\n' \"$CYAN\" \"$RESET\"\n  printf '[SG-Gateway] Мастер установки SG-Gateway 0.1.0-022.08 запущен\\n'\n",
)
