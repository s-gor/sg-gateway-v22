from __future__ import annotations

from pathlib import Path


def replace(path: str, old: str, new: str, *, expected: int = 1) -> None:
    target = Path(path)
    text = target.read_text(encoding="utf-8")
    actual = text.count(old)
    if actual != expected:
        raise SystemExit(
            f"{path}: expected {expected} occurrences, found {actual}: {old!r}"
        )
    target.write_text(text.replace(old, new), encoding="utf-8")


def insert_before(path: str, marker: str, addition: str) -> None:
    replace(path, marker, addition + marker)


# Backend: AWG31 is a normal explicit engine, not an invisible credential added
# to every device regardless of the selected protocol set.
replace(
    "app/clients/repository.py",
    '    "amneziawg",\n    "amneziawg3",\n    "xray",',
    '    "amneziawg",\n    "amneziawg3",\n    "amneziawg31",\n    "xray",',
)
replace(
    "app/clients/repository.py",
    '            "amneziawg,amneziawg3,xray_reality_tcp,xray_xhttp_reality,"',
    '            "amneziawg,amneziawg3,amneziawg31,xray_reality_tcp,xray_xhttp_reality,"',
)
replace(
    "app/clients/repository.py",
    '    for engine in [*engines, "amneziawg31"]:',
    "    for engine in engines:",
    expected=2,
)
replace(
    "app/clients/repository.py",
    '    wanted = set(engines) | {"amneziawg31"}',
    "    wanted = set(engines)",
)

# New-client picker.
replace(
    "app/web/templates/clients.html",
    "<strong>AmneziaWG 3</strong>",
    "<strong>AmneziaWG 3.0</strong>",
)
replace(
    "app/web/templates/clients.html",
    "AWG3 userspace · отдельная конфигурация и QR",
    "AWG 3.0 userspace · отдельная конфигурация и QR",
)
insert_before(
    "app/web/templates/clients.html",
    '      <label class="cv10-protocol"><input type="checkbox" name="protocols" value="mihomo" checked>',
    '      <label class="cv10-protocol"><input type="checkbox" name="protocols" value="amneziawg31"><span><strong>AmneziaWG 3.1</strong><small>AWG 3.1 userspace · отдельная конфигурация</small></span></label>\n',
)

# Add-device picker.
replace(
    "app/web/templates/client_detail.html",
    "<strong>AmneziaWG 3</strong>",
    "<strong>AmneziaWG 3.0</strong>",
)
replace(
    "app/web/templates/client_detail.html",
    "AWG3 userspace · отдельная конфигурация и QR",
    "AWG 3.0 userspace · отдельная конфигурация и QR",
)
insert_before(
    "app/web/templates/client_detail.html",
    '''        <label class="dv16-protocol {{ 'is-locked' if not tls.https_ready else '' }}">
          <input type="checkbox" name="protocols" value="anytls"''',
    '''        <label class="dv16-protocol">
          <input type="checkbox" name="protocols" value="amneziawg31">
          <span><strong>AmneziaWG 3.1</strong><small>AWG 3.1 userspace · отдельная конфигурация</small></span>
        </label>
''',
)

# Client/device edit pickers. Existing hidden credentials are surfaced as
# selected because device_access_tokens now recognises amneziawg31.
replace(
    "app/web/templates/_client_edit_dialogs.html",
    "<strong>AmneziaWG 3</strong>",
    "<strong>AmneziaWG 3.0</strong>",
    expected=2,
)
replace(
    "app/web/templates/_client_edit_dialogs.html",
    "AWG3 userspace · конфигурация и QR",
    "AWG 3.0 userspace · конфигурация и QR",
    expected=2,
)
insert_before(
    "app/web/templates/_client_edit_dialogs.html",
    "      {% set anytls_selected = 'anytls' in primary_tokens %}",
    '''      {% set awg31_selected = 'amneziawg31' in primary_tokens %}
      <label class="dv16-protocol">
        <input type="checkbox" name="protocols" value="amneziawg31" {% if awg31_selected %}checked{% endif %}>
        <span><strong>AmneziaWG 3.1</strong><small>{{ 'Подключён — существующие credentials сохраняются' if awg31_selected else 'AWG 3.1 userspace · конфигурация' }}</small></span>
      </label>
''',
)
insert_before(
    "app/web/templates/_client_edit_dialogs.html",
    "      {% set anytls_selected = 'anytls' in selected_tokens %}",
    '''      {% set device_awg31_selected = 'amneziawg31' in selected_tokens %}
      <label class="dv16-protocol">
        <input type="checkbox" name="protocols" value="amneziawg31" {% if device_awg31_selected %}checked{% endif %}>
        <span><strong>AmneziaWG 3.1</strong><small>{{ 'Подключён — существующие credentials сохраняются' if device_awg31_selected else 'AWG 3.1 userspace · конфигурация' }}</small></span>
      </label>
''',
)

# Client-detail JavaScript ordering and names.
replace(
    "app/web/static/sg-device-collapse-v1.js",
    "    'amneziawg3',\n    'mihomo',",
    "    'amneziawg3',\n    'amneziawg31',\n    'mihomo',",
)
replace(
    "app/web/static/sg-device-collapse-v1.js",
    "    setLabelTitle(byValue.get('amneziawg3'), 'AmneziaWG 3.1');",
    "    setLabelTitle(byValue.get('amneziawg3'), 'AmneziaWG 3.0');\n    setLabelTitle(byValue.get('amneziawg31'), 'AmneziaWG 3.1');",
)
replace(
    "app/web/static/sg-device-collapse-v1.js",
    "      setAvailableNote(byValue.get('amneziawg3'), 'UDP 586 · userspace-конфигурация и QR');",
    "      setAvailableNote(byValue.get('amneziawg3'), 'UDP 586 · userspace-конфигурация и QR');\n      setAvailableNote(byValue.get('amneziawg31'), 'UDP 587 · userspace-конфигурация');",
)

# Existing UI contract test must distinguish 3.0 from 3.1.
replace(
    "tests/test_sg_gateway_v22_clients_devices_ux.py",
    "def test_protocol_picker_is_unified_for_current_eight_protocols_only() -> None:",
    "def test_protocol_picker_distinguishes_awg30_and_awg31() -> None:",
)
replace(
    "tests/test_sg_gateway_v22_clients_devices_ux.py",
    "'amneziawg','amneziawg3','mihomo'",
    "'amneziawg','amneziawg3','amneziawg31','mihomo'",
)
replace(
    "tests/test_sg_gateway_v22_clients_devices_ux.py",
    "    assert \"setLabelTitle(byValue.get('amneziawg3'), 'AmneziaWG 3.1')\" in body",
    "    assert \"setLabelTitle(byValue.get('amneziawg3'), 'AmneziaWG 3.0')\" in body\n    assert \"setLabelTitle(byValue.get('amneziawg31'), 'AmneziaWG 3.1')\" in body",
)
replace(
    "tests/test_sg_gateway_v22_clients_devices_ux.py",
    "    assert \"setAvailableNote(byValue.get('amneziawg3'), 'UDP 586 · userspace-конфигурация и QR')\" in body",
    "    assert \"setAvailableNote(byValue.get('amneziawg3'), 'UDP 586 · userspace-конфигурация и QR')\" in body\n    assert \"setAvailableNote(byValue.get('amneziawg31'), 'UDP 587 · userspace-конфигурация')\" in body",
)

# Stage-2 tests intentionally exercise AWG31 and must select it explicitly.
replace(
    "tests/test_sg_gateway_v22_awg31_stage2_api_ui.py",
    '"amneziawg,amneziawg3"',
    '"amneziawg,amneziawg3,amneziawg31"',
    expected=4,
)
