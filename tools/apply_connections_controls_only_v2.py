from __future__ import annotations

import sys
from pathlib import Path

root = Path(sys.argv[1]).resolve()


def replace_once(path: str, old: str, new: str) -> None:
    file = root / path
    text = file.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{path}: expected one anchor, found {count}: {old[:120]!r}")
    file.write_text(text.replace(old, new, 1), encoding="utf-8")


# 1) Make the section truthful: controls are controls, fixed contracts become metadata.
replace_once(
    "app/web/templates/connections.html",
    """                <h3>Настройки выбранных профилей</h3>\n                <p>Показываются только параметры карточек, которые сейчас выбраны.</p>""",
    """                <h3>Параметры выбранных профилей</h3>\n                <p>Здесь только то, что можно изменить. Фиксированные параметры показаны компактно рядом с названием профиля.</p>""",
)

replace_once(
    "app/web/templates/connections.html",
    """                <div class=\"xps2-parameter-title\">\n                  <strong>{{ profile.title }}</strong>\n                  <span>{{ profile.transport }} · {{ profile.security }}</span>\n                </div>\n                <label>\n                  <span>{{ 'UDP-порт' if profile.id == 'hysteria2' else 'TCP-порт' }}</span>""",
    """                <div class=\"xps2-parameter-title\">\n                  <strong>{{ profile.title }}</strong>\n                  <span>{{ profile.transport }} · {{ profile.security }}</span>\n                  <div class=\"xps2-profile-meta\">\n                    {% if profile.flow %}<span>Vision · {{ profile.flow }}</span>{% endif %}\n                    {% if profile.id == 'xhttp_reality' %}<span>XHTTP client · stream-one</span>{% endif %}\n                    {% if profile.encryption_required %}<span class=\"{{ 'is-ready' if profile.encryption_ready else 'is-warning' }}\">VLESS Encryption · {{ 'готово' if profile.encryption_ready else 'не создано' }}</span>{% endif %}\n                    {% if not profile.path %}<span>Path · —</span>{% endif %}\n                  </div>\n                </div>\n                <label class=\"xps2-field-port\">\n                  <span>{{ 'UDP-порт' if profile.id == 'hysteria2' else 'TCP-порт' }}</span>""",
)

replace_once(
    "app/web/templates/connections.html",
    """                {% if profile.flow %}\n                <div class=\"xps2-flow-field\">\n                  <span>Flow</span>\n                  <strong>{{ profile.flow }}</strong>\n                  <small>Обязательный XTLS Vision для выбранного VLESS-профиля</small>\n                </div>\n                {% endif %}\n""",
    "",
)

replace_once(
    "app/web/templates/connections.html",
    """                {% if profile.mode %}\n                <label>\n                  <span>XHTTP mode клиента</span>\n                  <select name=\"{{ profile.id }}_mode\" {% if locked %}disabled{% endif %}>\n                    {% for item in xray_profiles.xhttp_mode_options %}\n                    <option value=\"{{ item.value }}\" {% if item.value == profile.mode %}selected{% endif %}>{{ item.title }} · {{ item.value }}</option>\n                    {% endfor %}\n                  </select>\n                  <small>Сервер остаётся в auto и принимает все четыре режима. Выбор меняет клиентские ссылки, QR и SG Client subscription.</small>\n                </label>\n\n                <section class=\"xps2-xmux\">""",
    """                {% if profile.mode %}\n                {% if profile.id == 'xhttp_reality' %}\n                <input type=\"hidden\" name=\"{{ profile.id }}_mode\" value=\"stream-one\">\n                {% else %}\n                <label class=\"xps2-field-mode\">\n                  <span>XHTTP mode клиента</span>\n                  <select name=\"{{ profile.id }}_mode\" {% if locked %}disabled{% endif %}>\n                    {% for item in xray_profiles.xhttp_mode_options %}\n                    <option value=\"{{ item.value }}\" {% if item.value == profile.mode %}selected{% endif %}>{{ item.title }} · {{ item.value }}</option>\n                    {% endfor %}\n                  </select>\n                  <small>Сервер остаётся в auto. Выбор меняет клиентские ссылки, QR и SG Client subscription.</small>\n                </label>\n                {% endif %}\n\n                <section class=\"xps2-xmux\">""",
)

replace_once(
    "app/web/templates/connections.html",
    """                {% if profile.encryption_required %}\n                <div class=\"xps2-flow-field\">\n                  <span>VLESS Encryption</span>\n                  <strong>{{ 'Готово' if profile.encryption_ready else 'Не создано' }}</strong>\n                  <small>Ключ клиента хранится в защищённых настройках и полностью здесь не показывается</small>\n                </div>\n                {% endif %}\n""",
    "",
)

replace_once(
    "app/web/templates/connections.html",
    """                {% if profile.path %}\n                <label>\n                  <span>Public Path</span>\n                  <input type=\"text\" name=\"{{ profile.id }}_path\" value=\"{{ profile.path }}\"\n                         {% if locked %}disabled{% endif %}>\n                </label>\n                {% else %}\n                <div class=\"xps2-parameter-note\">Без дополнительного Path</div>\n                {% endif %}""",
    """                {% if profile.path %}\n                <label class=\"xps2-field-path\">\n                  <span>Public Path</span>\n                  <input type=\"text\" name=\"{{ profile.id }}_path\" value=\"{{ profile.path }}\"\n                         {% if locked %}disabled{% endif %}>\n                </label>\n                {% endif %}""",
)

replace_once(
    "app/web/templates/connections.html",
    """                      <span class=\"xps2-salamander-kicker\">ОБФУСКАЦИЯ</span>\n                      <strong>Hysteria2 Obfuscation</strong>\n                      <p>Salamander остаётся совместимым базовым режимом. Gecko добавляет к нему фрагментацию QUIC handshake и случайный padding 512–1200 байт.</p>""",
    """                      <strong>Obfuscation</strong>\n                      <p>Off · Salamander · Gecko</p>""",
)

# 2) Reality XHTTP is now natively represented as a hidden stream-one form value.
# Remove the JS DOM replacement; the POST contract remains identical and simpler.
replace_once(
    "app/web/static/sg-xmux-settings-v1.js",
    """\n    // SG-Panel contract: Reality XHTTP client mode is fixed stream-one.\n    // The server remains auto; TLS keeps the existing four-mode selector.\n    const realityMode = document.querySelector('select[name=\"xhttp_reality_mode\"]');\n    if (realityMode) {\n      realityMode.value = 'stream-one';\n      const label = realityMode.closest('label');\n      if (label && !document.querySelector('[data-xmux-reality-fixed]')) {\n        const fixed = document.createElement('div');\n        fixed.className = 'xps2-flow-field xmux1-fixed-mode';\n        fixed.dataset.xmuxRealityFixed = '1';\n        fixed.innerHTML = '<span>XHTTP mode клиента</span><strong>Stream One · stream-one</strong><small>Фиксировано как в SG-Panel. Серверный XHTTP mode остаётся auto.</small>';\n\n        // Replacing the visible select must not remove the value from the main\n        // Xray Apply form. Keep the fixed client mode in the POST payload.\n        const hidden = document.createElement('input');\n        hidden.type = 'hidden';\n        hidden.name = 'xhttp_reality_mode';\n        hidden.value = 'stream-one';\n        fixed.appendChild(hidden);\n\n        label.replaceWith(fixed);\n      } else {\n        realityMode.disabled = true;\n      }\n    }\n""",
    """\n    // Reality XHTTP mode is rendered by the main form as a hidden stream-one\n    // value. TLS keeps its visible four-mode selector.\n""",
)

# 3) Replace the first visual experiment with a controls-only layout.
css_path = root / "app/web/static/sg-xmux-settings-v1.css"
css = css_path.read_text(encoding="utf-8")
marker = "/* SG-Gateway 022.04 · Connections protocol-card polish."
if css.count(marker) != 1:
    raise SystemExit(f"CSS polish marker count={css.count(marker)}")
prefix = css.split(marker, 1)[0].rstrip() + "\n\n"
polish = r'''/* SG-Gateway 022.04 · Connections controls-only polish.
   Only actual user controls occupy the form grid. Fixed protocol contracts are metadata. */
.xps2-parameters {
  padding: 16px;
}

.xps2-parameter-list {
  gap: 10px;
  margin-top: 14px;
}

.xps2-parameter-row {
  align-items: end;
  gap: 12px 14px;
  padding: 14px 16px;
  border-radius: 12px;
  box-shadow: none;
}

.xps2-parameter-title {
  display: grid;
  align-content: center;
  gap: 3px;
  min-width: 0;
  padding: 1px 8px 1px 0;
}

.xps2-parameter-title > strong {
  font-size: 14px;
  line-height: 1.25;
}

.xps2-parameter-title > span {
  color: var(--sg-muted);
  font-size: 10.5px;
  line-height: 1.35;
}

.xps2-profile-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 4px 6px;
  margin-top: 5px;
}

.xps2-profile-meta > span {
  display: inline-flex;
  align-items: center;
  min-height: 22px;
  padding: 2px 7px;
  border: 1px solid color-mix(in srgb, var(--sg-line) 78%, transparent);
  border-radius: 999px;
  color: var(--sg-muted);
  background: color-mix(in srgb, var(--sg-panel) 72%, transparent);
  font-size: 9px;
  font-weight: 650;
  line-height: 1.2;
  white-space: nowrap;
}

.xps2-profile-meta > span.is-ready {
  color: var(--sg-green);
  border-color: color-mix(in srgb, var(--sg-green) 32%, var(--sg-line));
}

.xps2-profile-meta > span.is-warning {
  color: var(--sg-warning, #b47d32);
}

.xps2-parameter-row > label {
  display: grid;
  align-content: end;
  min-width: 0;
  gap: 5px;
}

.xps2-parameter-row > label > span {
  color: var(--sg-muted);
  font-size: 9.5px;
  font-weight: 800;
  letter-spacing: .025em;
}

.xps2-parameter-row > label > small {
  margin-top: 1px;
  color: var(--sg-muted);
  font-size: 9.5px;
  line-height: 1.35;
}

.xps2-parameter-row > label input,
.xps2-parameter-row > label select {
  min-height: 42px;
}

.xps2-field-port { grid-area: port; }
.xps2-field-mode { grid-area: mode; }
.xps2-field-path { grid-area: path; }
.xps2-parameter-title { grid-area: title; }
.xps2-salamander { grid-area: obfs; }

.xps2-parameter-row[data-profile-panel="reality_tcp"] {
  grid-template-columns: minmax(300px, 1fr) minmax(150px, 210px);
  grid-template-areas: "title port";
}

.xps2-parameter-row[data-profile-panel="xhttp_reality"] {
  grid-template-columns: minmax(300px, .9fr) minmax(150px, 210px) minmax(320px, 1.35fr);
  grid-template-areas: "title port path";
}

.xps2-parameter-row[data-profile-panel="xhttp_tls"] {
  grid-template-columns: minmax(250px, .75fr) minmax(145px, 190px) minmax(245px, 1fr) minmax(300px, 1.2fr);
  grid-template-areas: "title port mode path";
}

.xps2-parameter-row[data-profile-panel="hysteria2"] {
  grid-template-columns: minmax(300px, 1fr) minmax(150px, 210px);
  grid-template-areas:
    "title port"
    "obfs obfs";
}

.xps2-salamander {
  display: grid;
  gap: 9px;
  margin-top: 2px;
  border: 0 !important;
  border-top: 1px solid var(--sg-line-soft) !important;
  border-radius: 0 !important;
  background: transparent !important;
  padding: 11px 0 0;
  box-shadow: none !important;
}

.xps2-salamander > header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.xps2-salamander > header > div {
  display: flex;
  align-items: baseline;
  flex-wrap: wrap;
  gap: 5px 9px;
}

.xps2-salamander > header strong {
  font-size: 13px;
}

.xps2-salamander > header p,
.xps2-salamander-warning,
.xps2-salamander-status {
  margin: 0;
  font-size: 10px;
  line-height: 1.4;
}

.xps2-salamander-version {
  min-height: 25px;
  padding: 0 8px;
  font-size: 8.5px;
}

.xps2-salamander-modes {
  gap: 7px;
}

.xps2-salamander-modes label,
.xps2-salamander-modes span {
  min-height: 34px;
}

.xps2-salamander-modes span {
  padding: 0 12px;
  font-size: 10.5px;
}

.xps2-salamander-secret {
  gap: 8px 10px;
}

.xps2-salamander-warning {
  border-left-width: 2px;
  padding: 7px 9px;
}

html[data-theme="light"] .xps2-parameter-row {
  background: color-mix(in srgb, var(--sg-ljd-ivory-high, #fbfaf6) 78%, transparent);
  border-color: color-mix(in srgb, var(--sg-ljd-border, #89968a) 72%, transparent);
}

html[data-theme="light"] .xps2-salamander {
  background: transparent !important;
  box-shadow: none !important;
}

@media (min-width: 981px) and (max-width: 1366px),
       (min-width: 981px) and (max-height: 820px) {
  .xps2-parameters {
    padding: 13px;
  }

  .xps2-parameter-row {
    gap: 9px 11px;
    padding: 11px 12px;
  }

  .xps2-parameter-row[data-profile-panel="reality_tcp"] {
    grid-template-columns: minmax(230px, 1fr) minmax(135px, 180px);
  }

  .xps2-parameter-row[data-profile-panel="xhttp_reality"] {
    grid-template-columns: minmax(230px, .8fr) minmax(135px, 180px) minmax(260px, 1.25fr);
  }

  .xps2-parameter-row[data-profile-panel="xhttp_tls"] {
    grid-template-columns: minmax(220px, .75fr) minmax(130px, 175px) minmax(220px, 1fr) minmax(250px, 1.1fr);
  }

  .xps2-parameter-row[data-profile-panel="hysteria2"] {
    grid-template-columns: minmax(230px, 1fr) minmax(135px, 180px);
  }

  .xps2-parameter-row > label input,
  .xps2-parameter-row > label select {
    min-height: 38px;
  }

  .xps2-profile-meta > span {
    min-height: 20px;
    padding: 1px 6px;
    font-size: 8.5px;
  }

  .xps2-salamander {
    gap: 7px;
    padding-top: 9px;
  }
}

@media (max-width: 1050px) {
  .xps2-parameter-row[data-profile-panel="reality_tcp"],
  .xps2-parameter-row[data-profile-panel="xhttp_reality"],
  .xps2-parameter-row[data-profile-panel="xhttp_tls"],
  .xps2-parameter-row[data-profile-panel="hysteria2"] {
    grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
  }

  .xps2-parameter-row[data-profile-panel="reality_tcp"] {
    grid-template-areas:
      "title port";
  }

  .xps2-parameter-row[data-profile-panel="xhttp_reality"] {
    grid-template-areas:
      "title port"
      "path path";
  }

  .xps2-parameter-row[data-profile-panel="xhttp_tls"] {
    grid-template-areas:
      "title port"
      "mode path";
  }

  .xps2-parameter-row[data-profile-panel="hysteria2"] {
    grid-template-areas:
      "title port"
      "obfs obfs";
  }
}

@media (max-width: 760px) {
  .xps2-parameter-row[data-profile-panel="reality_tcp"],
  .xps2-parameter-row[data-profile-panel="xhttp_reality"],
  .xps2-parameter-row[data-profile-panel="xhttp_tls"],
  .xps2-parameter-row[data-profile-panel="hysteria2"] {
    grid-template-columns: minmax(0, 1fr);
  }

  .xps2-parameter-row[data-profile-panel="reality_tcp"] {
    grid-template-areas: "title" "port";
  }

  .xps2-parameter-row[data-profile-panel="xhttp_reality"] {
    grid-template-areas: "title" "port" "path";
  }

  .xps2-parameter-row[data-profile-panel="xhttp_tls"] {
    grid-template-areas: "title" "port" "mode" "path";
  }

  .xps2-parameter-row[data-profile-panel="hysteria2"] {
    grid-template-areas: "title" "port" "obfs";
  }

  .xps2-salamander > header {
    align-items: flex-start;
    flex-direction: column;
  }

  .xps2-profile-meta > span {
    white-space: normal;
  }
}
'''
css_path.write_text(prefix + polish, encoding="utf-8")

# 4) Replace v1 visual assertions with controls-only regression coverage.
test_path = root / "tests/test_ui_connections_visual_v1.py"
test = test_path.read_text(encoding="utf-8")
start = test.index("\ndef test_connections_protocol_cards_have_explicit_profile_grid_areas():")
test = test[:start] + r'''

def test_connections_protocol_cards_show_only_real_controls_as_fields():
    template = (ROOT / "app/web/templates/connections.html").read_text(encoding="utf-8")
    css = (ROOT / "app/web/static/sg-xmux-settings-v1.css").read_text(encoding="utf-8")
    polish = css.split("SG-Gateway 022.04 · Connections controls-only polish", 1)[1]
    assert "Здесь только то, что можно изменить" in template
    for field_class in ("xps2-field-port", "xps2-field-mode", "xps2-field-path"):
        assert field_class in template
    for meta in ("xps2-profile-meta", "Vision · {{ profile.flow }}", "XHTTP client · stream-one", "VLESS Encryption ·"):
        assert meta in template
    assert "Без дополнительного Path" not in template
    assert "Обязательный XTLS Vision для выбранного VLESS-профиля" not in template
    assert "Ключ клиента хранится в защищённых настройках" not in template
    assert ".xps2-profile-meta" in polish
    assert ".xps2-field-port" in polish
    assert ".xps2-field-mode" in polish
    assert ".xps2-field-path" in polish
    assert "display: none" not in polish


def test_reality_xhttp_fixed_mode_is_native_hidden_form_value_not_fake_control():
    template = (ROOT / "app/web/templates/connections.html").read_text(encoding="utf-8")
    js = (ROOT / "app/web/static/sg-xmux-settings-v1.js").read_text(encoding="utf-8")
    assert "{% if profile.id == 'xhttp_reality' %}" in template
    assert '<input type="hidden" name="{{ profile.id }}_mode" value="stream-one">' in template
    assert "data-xmux-reality-fixed" not in js
    assert "label.replaceWith" not in js
    assert "Reality XHTTP mode is rendered by the main form as a hidden stream-one" in js


def test_connections_protocol_cards_keep_all_mutable_form_contracts():
    template = (ROOT / "app/web/templates/connections.html").read_text(encoding="utf-8")
    for field in (
        'name="{{ profile.id }}_port"',
        'name="{{ profile.id }}_mode"',
        'name="{{ profile.id }}_path"',
        'name="hysteria2_obfs_mode"',
        'name="hysteria2_obfs_password"',
        'name="hysteria2_obfs_rotate"',
    ):
        assert field in template
    for value in ('value="none"', 'value="salamander"', 'value="gecko"'):
        assert value in template
    assert "Проверить конфигурацию" in template
    assert "Сохранить и применить" in template


def test_connections_protocol_cards_have_compact_profile_specific_grids():
    css = (ROOT / "app/web/static/sg-xmux-settings-v1.css").read_text(encoding="utf-8")
    polish = css.split("SG-Gateway 022.04 · Connections controls-only polish", 1)[1]
    for profile_id in ("reality_tcp", "xhttp_reality", "xhttp_tls", "hysteria2"):
        assert f'data-profile-panel="{profile_id}"' in polish
    assert 'grid-template-areas: "title port";' in polish
    assert 'grid-template-areas: "title port path";' in polish
    assert 'grid-template-areas: "title port mode path";' in polish
    assert '"obfs obfs"' in polish
    assert "box-shadow: none" in polish


def test_connections_protocol_cards_cover_low_resolution_and_mobile():
    css = (ROOT / "app/web/static/sg-xmux-settings-v1.css").read_text(encoding="utf-8")
    polish = css.split("SG-Gateway 022.04 · Connections controls-only polish", 1)[1]
    assert "@media (min-width: 981px) and (max-width: 1366px)" in polish
    assert "(min-width: 981px) and (max-height: 820px)" in polish
    assert "@media (max-width: 1050px)" in polish
    assert "@media (max-width: 760px)" in polish
    assert 'grid-template-areas: "title" "port" "mode" "path";' in polish
'''
test_path.write_text(test, encoding="utf-8")

# 5) XMUX contract test now validates the native hidden input instead of DOM replacement.
xmux_test = root / "tests/test_sg_gateway_02204_xmux_sgpanel_contract.py"
text = xmux_test.read_text(encoding="utf-8")
old = """    assert \"stream-one\" in js\n    assert \"hidden.name = 'xhttp_reality_mode'\" in js\n    assert \"hidden.value = 'stream-one'\" in js"""
new = """    assert '<input type=\"hidden\" name=\"{{ profile.id }}_mode\" value=\"stream-one\">' in template\n    assert \"Reality XHTTP mode is rendered by the main form as a hidden stream-one\" in js\n    assert \"label.replaceWith\" not in js"""
if text.count(old) != 1:
    raise SystemExit(f"XMUX UI test anchor count={text.count(old)}")
xmux_test.write_text(text.replace(old, new, 1), encoding="utf-8")

print("Connections controls-only v2 patch prepared")
