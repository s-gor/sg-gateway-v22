from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    target = Path(path)
    text = target.read_text(encoding="utf-8")
    if text.count(old) != 1:
        raise SystemExit(f"expected exactly one match in {path}: {old[:80]!r}")
    target.write_text(text.replace(old, new, 1), encoding="utf-8")


replace_once(
    "app/web/templates/connections.html",
    '      <div class="awgd-grid">\n',
    '      <div class="awgd-inner-rail sg-ui-rail">\n      <div class="awgd-grid">\n',
)
replace_once(
    "app/web/templates/connections.html",
    '      </section>\n    </article>\n\n    {% include "_mihomo_panel.html" %}',
    '      </section>\n      </div>\n    </article>\n\n    {% include "_mihomo_panel.html" %}',
)
replace_once(
    "app/web/templates/_mihomo_panel.html",
    '  <div class="mhv2-compact-meta">\n',
    '  <div class="mhv2-inner-rail sg-ui-rail">\n  <div class="mhv2-compact-meta">\n',
)
replace_once(
    "app/web/templates/_mihomo_panel.html",
    '  </p>\n</section>\n\n<style>',
    '  </p>\n  </div>\n</section>\n\n<style>',
)

css_path = Path("app/web/static/sg-ui-connections-v22-08.css")
css = css_path.read_text(encoding="utf-8")
magic = """/* Match the lower NaiveProxy content rail without widening NaiveProxy itself. */
body.page-connections .awgd-shell {
  padding-inline: var(--sg-ui-card-pad, 18px);
}

body.page-connections .mhv2-panel {
  padding-inline: calc(var(--sg-ui-card-pad, 18px) + 18px);
}

"""
mobile = """
@media (max-width: 620px) {
  body.page-connections .awgd-grid {
    padding-inline: 18px;
  }

  body.page-connections .awgd-shared-dns {
    margin-inline: 18px;
  }
}
"""
if css.count(magic) != 1 or css.count(mobile) != 1:
    raise SystemExit("unexpected Connections CSS before canonical-rail migration")
css = css.replace(magic, "", 1).replace(mobile, "\n", 1)
if "calc(" in css or "margin-inline" in css:
    raise SystemExit("forbidden cumulative rail offset remains")
css_path.write_text(css, encoding="utf-8")
