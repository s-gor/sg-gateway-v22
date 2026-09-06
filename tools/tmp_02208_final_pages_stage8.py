from __future__ import annotations

import re
from pathlib import Path

HELP_CONTRACT = r'''from __future__ import annotations
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
T = (ROOT / "app/web/templates/help.html").read_text(encoding="utf-8")


def test_02208_help_assets_semantics_and_behavior() -> None:
    assert "{% block page_styles %}" in T
    assert "{% block head %}" not in T
    assert "static_asset('sg-ui-help-v22-08.css')" in T
    assert not (ROOT / "app/web/static/sg-help-visual-v1.css").exists()
    assert (ROOT / "app/web/static/sg-ui-help-v22-08.css").exists()
    for marker in ('data-sg-ui-page="help"', 'data-sg-section="help-head"', 'data-sg-section="help-summary"', 'data-sg-section="help-search"', 'data-sg-section="help-workspace"', 'sg-ui-page', 'sg-ui-page-head', 'sg-ui-actions', 'sg-ui-section'):
        assert marker in T, marker
    for marker in ('id="help-search"', 'id="help-clear"', 'id="help-no-results"', 'data-help-topic', 'data-search=', 'input.addEventListener("input"', 'clear.addEventListener("click"'):
        assert marker in T, marker
    for endpoint in ("system", "maintenance", "connections", "routing", "clients", "security", "help_topic", "help_index", "recovery", "download_diagnostics"):
        assert f"url_for('{endpoint}'" in T, endpoint
'''

STANDALONE_CONTRACT = r'''from __future__ import annotations
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOGIN = (ROOT / "app/web/templates/login.html").read_text(encoding="utf-8")
RECOVERY = (ROOT / "app/web/templates/recovery.html").read_text(encoding="utf-8")


def _canonical(template: str) -> None:
    for asset in ("sg-ui-foundation-v22-08.css", "sg-ui-components-v22-08.css", "sg-ui-standalone-v22-08.css"):
        assert f"static_asset('{asset}')" in template, asset
    for legacy in ("app.css", "sg-luxury-jade-depth-v2.css", "sg-readable-typography-v3.css"):
        assert legacy not in template, legacy
    assert "?v=" not in template


def test_02208_login_is_standalone_and_preserves_form_contract() -> None:
    _canonical(LOGIN)
    assert 'data-sg-standalone-page="login"' in LOGIN
    assert '<form class="settings-form sg-ui-standalone-form" method="post" action="/login">' in LOGIN
    assert 'name="next" value="{{ next_url }}"' in LOGIN
    assert 'name="password" type="password" autocomplete="current-password" autofocus required' in LOGIN
    assert 'type="submit"' in LOGIN
    assert 'sg-ui-button' in LOGIN


def test_02208_recovery_is_standalone_and_preserves_restore_contract() -> None:
    _canonical(RECOVERY)
    assert "static_asset('sg-recovery-restore-v1.css')" in RECOVERY
    assert 'data-sg-standalone-page="recovery"' in RECOVERY
    for marker in ('id="recovery-confirm"', 'id="recovery-restore-form"', 'id="recovery-confirm-cancel"', 'data-recovery-restore', 'data-backup-name=', 'data-restore-url=', 'requestedRestore = {{ requested_restore|tojson }}'):
        assert marker in RECOVERY, marker
    assert "url_for('download_backup_route', name=backup.name)" in RECOVERY
    assert "url_for('recovery_restore_backup_route', name=backup.name)" in RECOVERY
    for href in ('href="/maintenance"', 'href="/maintenance/diagnostics.json"', 'href="/"'):
        assert href in RECOVERY
    assert 'recovery-restore-button sg-ui-button' in RECOVERY
'''

OP_CONTRACT = r'''from __future__ import annotations
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
T = (ROOT / "app/web/templates/operation_job.html").read_text(encoding="utf-8")


def test_02208_operation_job_assets_semantics_and_polling_contract() -> None:
    assert "{% block page_styles %}" in T
    assert "{% block head %}" not in T
    assert "static_asset('sg-ui-operation-job-v22-08.css')" in T
    assert not (ROOT / "app/web/static/sg-operation-job-v13.css").exists()
    assert (ROOT / "app/web/static/sg-ui-operation-job-v22-08.css").exists()
    for marker in ('data-sg-ui-page="operation-job"', 'data-sg-section="operation-head"', 'data-sg-section="operation-terminal"', 'data-sg-section="operation-actions"', 'sg-ui-page', 'sg-ui-page-head', 'sg-ui-actions'):
        assert marker in T, marker
    for marker in ('data-kind="{{ job.kind }}"', 'data-restart-expected=', 'data-target-url=', 'data-status-url=', 'id="opjob-log"', 'id="opjob-status"', 'id="opjob-target"', 'id="opjob-refresh"', 'id="opjob-return-gateway"', "fetch(root.dataset.statusUrl", "window.setTimeout(update", "window.location.replace"):
        assert marker in T, marker
    assert "url_for('operation_job_status', job_id=job.job_id)" in T
'''

GEOMETRY = r'''from __future__ import annotations
import math
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
VIEWPORTS = ({"width":1440,"height":900},{"width":1024,"height":820},{"width":390,"height":760})


def close(a,b,t=1.0): assert math.isclose(a,b,abs_tol=t),(a,b)


def _shell_geometry(css_name: str, html: str, selectors: tuple[str,...]) -> None:
    foundation=(ROOT/"app/web/static/sg-ui-foundation-v22-08.css").read_text(encoding="utf-8")
    layout=(ROOT/"app/web/static/sg-ui-layout-v22-08.css").read_text(encoding="utf-8")
    components=(ROOT/"app/web/static/sg-ui-components-v22-08.css").read_text(encoding="utf-8")
    css=(ROOT/f"app/web/static/{css_name}").read_text(encoding="utf-8")
    with sync_playwright() as p:
        browser=p.chromium.launch()
        try:
            for viewport in VIEWPORTS:
                by_theme={}
                for theme in ("dark","light"):
                    page=browser.new_page(viewport=viewport)
                    page.set_content(html)
                    for layer in (foundation,layout,components,css): page.add_style_tag(content=layer)
                    page.evaluate("t=>document.documentElement.dataset.theme=t",theme)
                    assert page.evaluate("document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1")
                    boxes={s:page.locator(s).bounding_box() for s in selectors}; root=boxes[selectors[0]]; assert root
                    for s in selectors[1:]:
                        b=boxes[s]; assert b; close(root["x"],b["x"]); close(root["width"],b["width"])
                    by_theme[theme]=boxes; page.close()
                for s in selectors:
                    close(by_theme["dark"][s]["x"],by_theme["light"][s]["x"]); close(by_theme["dark"][s]["width"],by_theme["light"][s]["width"])
        finally: browser.close()


def test_02208_help_and_operation_outer_rails() -> None:
    _shell_geometry("sg-ui-help-v22-08.css", """<body style='margin:0'><main class='sg-content'><section class='sg-ui-page' data-sg-ui-page='help'><header class='sg-ui-page-head' data-sg-section='help-head'>H</header><section class='sg-ui-section' data-sg-section='help-search'>S</section><section class='sg-ui-section' data-sg-section='help-workspace'>W</section></section></main></body>""", ('[data-sg-ui-page="help"]','[data-sg-section="help-head"]','[data-sg-section="help-search"]','[data-sg-section="help-workspace"]'))
    _shell_geometry("sg-ui-operation-job-v22-08.css", """<body style='margin:0'><main class='sg-content'><section class='sg-ui-page' data-sg-ui-page='operation-job'><header class='sg-ui-page-head' data-sg-section='operation-head'>H</header><article data-sg-section='operation-terminal'>T</article><footer class='sg-ui-actions' data-sg-section='operation-actions'>A</footer></section></main></body>""", ('[data-sg-ui-page="operation-job"]','[data-sg-section="operation-head"]','[data-sg-section="operation-terminal"]','[data-sg-section="operation-actions"]'))


def test_02208_standalone_pages_have_responsive_theme_invariant_frame() -> None:
    foundation=(ROOT/"app/web/static/sg-ui-foundation-v22-08.css").read_text(encoding="utf-8")
    components=(ROOT/"app/web/static/sg-ui-components-v22-08.css").read_text(encoding="utf-8")
    standalone=(ROOT/"app/web/static/sg-ui-standalone-v22-08.css").read_text(encoding="utf-8")
    cases=(
      ("""<body class='sg-ui-standalone-body'><main class='sg-ui-standalone sg-ui-standalone--login' data-sg-standalone-page='login'><section class='sg-ui-card sg-ui-login-card'>Login</section></main></body>""",'[data-sg-standalone-page="login"]','.sg-ui-login-card'),
      ("""<body class='sg-ui-standalone-body'><main class='sg-ui-standalone sg-ui-standalone--recovery' data-sg-standalone-page='recovery'><header class='sg-ui-recovery-head'>Recovery</header><section class='tool-panel'>Health</section><section class='table-panel'>Backups</section></main></body>""",'[data-sg-standalone-page="recovery"]','.tool-panel'),
    )
    with sync_playwright() as p:
        browser=p.chromium.launch()
        try:
            for viewport in VIEWPORTS:
                for html,root_sel,child_sel in cases:
                    geom={}
                    for theme in ("dark","light"):
                        page=browser.new_page(viewport=viewport); page.set_content(html)
                        for layer in (foundation,components,standalone): page.add_style_tag(content=layer)
                        page.evaluate("t=>document.documentElement.dataset.theme=t",theme)
                        assert page.evaluate("document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1")
                        root=page.locator(root_sel).bounding_box(); child=page.locator(child_sel).bounding_box(); assert root and child
                        assert root["x"] >= -1 and root["x"]+root["width"] <= viewport["width"]+1
                        assert child["x"] >= root["x"]-1 and child["x"]+child["width"] <= root["x"]+root["width"]+1
                        geom[theme]=(root,child); page.close()
                    for idx in (0,1):
                        close(geom["dark"][idx]["x"],geom["light"][idx]["x"]); close(geom["dark"][idx]["width"],geom["light"][idx]["width"])
        finally: browser.close()
'''

STANDALONE_CSS = r'''/* SG-Gateway 22.08 standalone Login/Recovery layout. No authenticated shell ownership. */
:root {
  --bg: var(--sg-ui-bg); --panel: var(--sg-ui-surface); --panel-soft: var(--sg-ui-surface-raised);
  --line: var(--sg-ui-border); --text: var(--sg-ui-text); --muted: var(--sg-ui-text-muted);
  --green: var(--sg-ui-accent); --blue: var(--sg-ui-info); --button: var(--sg-ui-surface-raised); --danger: var(--sg-ui-danger);
}
* { box-sizing: border-box; }
html, body { min-width: 320px; min-height: 100%; }
body.sg-ui-standalone-body { margin: 0; background: var(--sg-ui-bg); color: var(--sg-ui-text); font-family: Inter,"Segoe UI",system-ui,-apple-system,BlinkMacSystemFont,sans-serif; }
.sg-ui-standalone { width: min(1120px,100%); margin-inline: auto; padding: 32px; }
.sg-ui-standalone--login { display: grid; min-height: 100vh; place-items: center; }
.sg-ui-login-card { width: min(420px,100%); }
.brand { display:flex; gap:12px; align-items:center; margin-bottom:28px; }
.brand-mark { display:grid; width:42px; height:42px; place-items:center; border-radius:10px; background:var(--sg-ui-info); color:var(--sg-ui-bg); font-weight:800; }
.brand-name { font-size:18px; font-weight:750; }
.brand-note { margin-top:2px; color:var(--sg-ui-text-muted); font-size:13px; }
.sg-ui-standalone-form { display:grid; gap:12px; }
.sg-ui-standalone-form label { display:grid; gap:8px; color:var(--sg-ui-text-muted); font-size:13px; }
.sg-ui-standalone-form input { width:100%; min-height:var(--sg-ui-control-height); padding-inline:12px; border:1px solid var(--sg-ui-border-strong); border-radius:var(--sg-ui-control-radius); background:var(--sg-ui-surface-nested); color:var(--sg-ui-text); font:inherit; }
.error-text { color:var(--sg-ui-danger); }
.sg-ui-recovery-head { display:flex; align-items:flex-start; justify-content:space-between; gap:24px; margin-bottom:26px; }
.sg-ui-recovery-head .brand { margin-bottom:0; }
.topbar-actions,.recovery-backup-actions,.recovery-confirm-actions { display:flex; flex-wrap:wrap; gap:10px; }
.flash-stack { display:grid; gap:10px; margin-bottom:18px; }
.flash-message { padding:12px 14px; border:1px solid var(--sg-ui-border); border-radius:var(--sg-ui-control-radius); background:var(--sg-ui-surface); color:var(--sg-ui-text); }
.flash-message.success { color:var(--sg-ui-accent); }.flash-message.error { color:var(--sg-ui-danger); }
.tool-panel,.table-panel { margin-bottom:14px; overflow:hidden; border:1px solid var(--sg-ui-border); border-radius:var(--sg-ui-card-radius); background:var(--sg-ui-surface); }
.tool-panel { padding:var(--sg-ui-card-pad); }
.section-heading h1 { margin:0 0 6px; }.section-heading p { margin:0; color:var(--sg-ui-text-muted); line-height:1.5; }
.data-table { width:100%; border-collapse:collapse; }.data-table th,.data-table td { padding:14px; border-bottom:1px solid var(--sg-ui-border); text-align:left; vertical-align:middle; }.data-table th { color:var(--sg-ui-text-muted); font-size:13px; font-weight:600; }.data-table tr:last-child td { border-bottom:0; }
.actions-cell { width:1%; white-space:nowrap; }.badge { display:inline-flex; padding:7px 10px; border:1px solid var(--sg-ui-border); border-radius:999px; color:var(--sg-ui-text-muted); }.badge.success { color:var(--sg-ui-accent); }.empty-state { padding:28px; }
@media (max-width:760px) { .sg-ui-standalone { padding:18px 16px 28px; } .sg-ui-recovery-head { display:grid; } .topbar-actions { justify-content:flex-start; } .data-table { display:block; overflow-x:auto; } }
'''


def write_tests() -> None:
    Path("tests/test_sg_gateway_v22_help_contract_02208.py").write_text(HELP_CONTRACT, encoding="utf-8")
    Path("tests/test_sg_gateway_v22_standalone_contract_02208.py").write_text(STANDALONE_CONTRACT, encoding="utf-8")
    Path("tests/test_sg_gateway_v22_operation_job_contract_02208.py").write_text(OP_CONTRACT, encoding="utf-8")
    Path("tests/test_sg_gateway_v22_final_pages_geometry_02208.py").write_text(GEOMETRY, encoding="utf-8")


def _remove_rule(css: str, selector: str) -> str:
    pattern=re.compile(rf"(?ms)^{re.escape(selector)}\s*\{{.*?^\}}\s*\n?")
    css,count=pattern.subn("",css,1)
    if count != 1: raise RuntimeError(f"expected rule {selector}, found {count}")
    return css


def migrate_help() -> None:
    path=Path("app/web/templates/help.html"); t=path.read_text(encoding="utf-8")
    start=t.index("{% block head %}"); end=t.index("{% endblock %}",start)+len("{% endblock %}")
    t=t[:start]+"{% block page_styles %}\n  <link rel=\"stylesheet\" href=\"{{ static_asset('sg-ui-help-v22-08.css') }}\">\n{% endblock %}"+t[end:]
    reps=(
      ('<section class="hlpv1-page">','<section class="hlpv1-page sg-ui-page sg-ui-help" data-sg-ui-page="help">'),
      ('<header class="hlpv1-heading">','<header class="hlpv1-heading sg-ui-page-head sg-ui-help-head" data-sg-section="help-head">'),
      ('<div class="hlpv1-heading-actions">','<div class="hlpv1-heading-actions sg-ui-actions">'),
      ('<section class="hlpv1-summary sg-ljd-strip">','<section class="hlpv1-summary sg-ljd-strip sg-ui-section" data-sg-section="help-summary">'),
      ('<section class="hlpv1-search-panel sg-ljd-card">','<section class="hlpv1-search-panel sg-ljd-card sg-ui-section" data-sg-section="help-search">'),
      ('<section class="hlpv1-workspace">','<section class="hlpv1-workspace sg-ui-section" data-sg-section="help-workspace">'),
    )
    for old,new in reps:
        if old not in t: raise RuntimeError(f"missing Help marker {old}")
        t=t.replace(old,new,1)
    path.write_text(t,encoding="utf-8")
    legacy=Path("app/web/static/sg-help-visual-v1.css"); css=legacy.read_text(encoding="utf-8")
    css=_remove_rule(css,".hlpv1-page"); css=_remove_rule(css,".hlpv1-heading")
    css+='''\n/* 22.08 semantic page ownership */\n[data-sg-ui-page="help"] { --sg-ui-page-gap:18px; min-width:0; }\n.sg-ui-help-head { align-items:flex-end; }\n[data-sg-ui-page="help"] > .sg-ui-section { width:100%; margin-inline:0; }\n@media(max-width:760px){ .sg-ui-help-head { align-items:stretch; } }\n'''
    Path("app/web/static/sg-ui-help-v22-08.css").write_text(css,encoding="utf-8"); legacy.unlink()


def migrate_login() -> None:
    path=Path("app/web/templates/login.html"); t=path.read_text(encoding="utf-8")
    for old in (
      '    <link rel="stylesheet" href="{{ url_for(\'static\', filename=\'app.css\') }}">\n',
      '    <link rel="stylesheet" href="{{ url_for(\'static\', filename=\'sg-luxury-jade-depth-v2.css\') }}">\n',
      '    <link rel="stylesheet" href="{{ url_for(\'static\', filename=\'sg-readable-typography-v3.css\') }}">\n',
    ):
        if old not in t: raise RuntimeError(f"login asset marker missing {old}")
        t=t.replace(old,"",1)
    marker='    <title>SG-Gateway · Вход</title>\n'
    assets=marker+''.join(f'    <link rel="stylesheet" href="{{{{ static_asset(\'{a}\') }}}}">\n' for a in ("sg-ui-foundation-v22-08.css","sg-ui-components-v22-08.css","sg-ui-standalone-v22-08.css"))
    t=t.replace(marker,assets,1)
    t=t.replace('<body class="sg-body">','<body class="sg-ui-standalone-body">',1)
    t=t.replace('<main class="login-shell">','<main class="login-shell sg-ui-standalone sg-ui-standalone--login" data-sg-standalone-page="login">',1)
    t=t.replace('<section class="login-panel sg-ljd-card">','<section class="login-panel sg-ui-card sg-ui-login-card">',1)
    t=t.replace('<form class="settings-form" method="post" action="/login">','<form class="settings-form sg-ui-standalone-form" method="post" action="/login">',1)
    t=t.replace('<button class="button primary sg-ljd-key-action" type="submit">','<button class="button primary sg-ljd-key-action sg-ui-button sg-ui-button--primary" type="submit">',1)
    path.write_text(t,encoding="utf-8")


def migrate_recovery() -> None:
    path=Path("app/web/templates/recovery.html"); t=path.read_text(encoding="utf-8")
    old_links=re.findall(r'^\s*<link rel="stylesheet" href="\{\{ url_for\(\'static\', filename=\'(app\.css|sg-luxury-jade-depth-v2\.css|sg-readable-typography-v3\.css)\'\) \}\}">\n?',t,re.M)
    if len(old_links)!=3: raise RuntimeError(f"unexpected Recovery old links {old_links}")
    t=re.sub(r'^\s*<link rel="stylesheet" href="\{\{ url_for\(\'static\', filename=\'(?:app\.css|sg-luxury-jade-depth-v2\.css|sg-readable-typography-v3\.css)\'\) \}\}">\n?','',t,flags=re.M)
    old='    <link rel="stylesheet" href="{{ url_for(\'static\', filename=\'sg-recovery-restore-v1.css\') }}?v={{ app_version }}-recovery-restore-v1">\n'
    if old not in t: raise RuntimeError("Recovery restore stylesheet marker missing")
    t=t.replace(old,"",1)
    marker='    <title>SG-Gateway · Recovery</title>\n'
    assets=marker+''.join(f'    <link rel="stylesheet" href="{{{{ static_asset(\'{a}\') }}}}">\n' for a in ("sg-ui-foundation-v22-08.css","sg-ui-components-v22-08.css","sg-ui-standalone-v22-08.css","sg-recovery-restore-v1.css"))
    t=t.replace(marker,assets,1)
    t=t.replace('<body class="sg-body">','<body class="sg-ui-standalone-body">',1)
    t=t.replace('<main class="recovery-shell">','<main class="recovery-shell sg-ui-standalone sg-ui-standalone--recovery" data-sg-standalone-page="recovery">',1)
    t=t.replace('<header class="recovery-header">','<header class="recovery-header sg-ui-recovery-head">',1)
    t=t.replace('<div class="topbar-actions">','<div class="topbar-actions sg-ui-actions">',1)
    t=t.replace('class="button primary"','class="button primary sg-ui-button sg-ui-button--primary"')
    t=t.replace('class="button small recovery-restore-button"','class="button small recovery-restore-button sg-ui-button sg-ui-button--small"')
    t=t.replace('class="button small"','class="button small sg-ui-button sg-ui-button--small"')
    t=t.replace('class="button recovery-restore-button"','class="button recovery-restore-button sg-ui-button"')
    t=t.replace('class="button"','class="button sg-ui-button"')
    path.write_text(t,encoding="utf-8")


def migrate_operation() -> None:
    path=Path("app/web/templates/operation_job.html"); t=path.read_text(encoding="utf-8")
    start=t.index("{% block head %}"); end=t.index("{% endblock %}",start)+len("{% endblock %}")
    t=t[:start]+"{% block page_styles %}\n  <link rel=\"stylesheet\" href=\"{{ static_asset('sg-ui-operation-job-v22-08.css') }}\">\n{% endblock %}"+t[end:]
    old='<section class="opjob-page"\n'; new='<section class="opjob-page sg-ui-page sg-ui-operation-job" data-sg-ui-page="operation-job"\n'
    if old not in t: raise RuntimeError("Operation page marker missing")
    t=t.replace(old,new,1)
    t=t.replace('<header class="opjob-head">','<header class="opjob-head sg-ui-page-head" data-sg-section="operation-head">',1)
    t=t.replace('<article class="opjob-terminal">','<article class="opjob-terminal" data-sg-section="operation-terminal">',1)
    t=t.replace('<footer class="opjob-actions">','<footer class="opjob-actions sg-ui-actions" data-sg-section="operation-actions">',1)
    path.write_text(t,encoding="utf-8")
    legacy=Path("app/web/static/sg-operation-job-v13.css"); css=legacy.read_text(encoding="utf-8")
    old_rule='.opjob-page{display:grid;gap:18px}'
    if old_rule not in css: raise RuntimeError("Operation outer page CSS marker missing")
    css=css.replace(old_rule,'[data-sg-ui-page="operation-job"]{--sg-ui-page-gap:18px}',1)
    Path("app/web/static/sg-ui-operation-job-v22-08.css").write_text(css,encoding="utf-8"); legacy.unlink()


def migrate() -> None:
    migrate_help(); migrate_login(); migrate_recovery(); migrate_operation()
    Path("app/web/static/sg-ui-standalone-v22-08.css").write_text(STANDALONE_CSS,encoding="utf-8")