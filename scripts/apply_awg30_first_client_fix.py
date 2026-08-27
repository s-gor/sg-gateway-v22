from __future__ import annotations

from pathlib import Path


clients_path = Path("app/web/templates/clients.html")
clients = clients_path.read_text(encoding="utf-8")
old_clients_card = """      <label class=\"cv10-protocol {{ 'is-locked' if awg3_runtime.known and not awg3_runtime.ready else '' }}\">
        <input type=\"checkbox\" name=\"protocols\" value=\"amneziawg3\" {% if awg3_runtime.known and not awg3_runtime.ready %}disabled{% endif %}>
        <span><strong>AmneziaWG 3.0</strong><small>{{ 'AWG3 runtime требует восстановления в Maintenance' if awg3_runtime.known and not awg3_runtime.ready else 'AWG 3.0 userspace · отдельная конфигурация и QR' }}</small></span>
      </label>"""
new_clients_card = """      <label class=\"cv10-protocol\">
        <input type=\"checkbox\" name=\"protocols\" value=\"amneziawg3\">
        <span><strong>AmneziaWG 3.0</strong><small>AWG 3.0 userspace · отдельная конфигурация и QR</small></span>
      </label>"""
old_warning = """    {% if awg3_runtime.known and not awg3_runtime.ready %}
    <div class=\"cv2-filter-footer\" data-awg3-runtime-warning>
      AWG3 временно недоступен. <a href=\"{{ url_for('maintenance', tab='updates') }}\">Открыть Maintenance → AWG3 Runtime</a>.
    </div>
    {% endif %}
"""
runtime_set = "{% set awg3_runtime = runtime_engine_state('amneziawg3') if runtime_engine_state is defined else {'known': false, 'ready': true, 'missing': []} %}\n"
if clients.count(old_clients_card) != 1:
    raise SystemExit(
        f"expected one gated AWG3.0 create card, found {clients.count(old_clients_card)}"
    )
if clients.count(old_warning) != 1:
    raise SystemExit(f"expected one AWG3.0 warning block, found {clients.count(old_warning)}")
if clients.count(runtime_set) != 1:
    raise SystemExit(f"expected one AWG3.0 runtime set, found {clients.count(runtime_set)}")
clients = clients.replace(old_clients_card, new_clients_card)
clients = clients.replace(old_warning, "")
clients = clients.replace(runtime_set, "")
clients_path.write_text(clients, encoding="utf-8")

edits_path = Path("app/web/templates/_client_edit_dialogs.html")
edits = edits_path.read_text(encoding="utf-8")
old_client_edit = """      {% set awg3_selected = 'amneziawg3' in primary_tokens %}
      <label class=\"dv16-protocol {{ 'is-locked' if awg3_runtime.known and not awg3_runtime.ready and not awg3_selected else '' }}\">
        <input type=\"checkbox\" name=\"protocols\" value=\"amneziawg3\" {% if awg3_selected %}checked{% endif %} {% if awg3_runtime.known and not awg3_runtime.ready and not awg3_selected %}disabled{% endif %}>
        <span><strong>AmneziaWG 3.0</strong><small>{% if awg3_selected %}Подключён — существующие credentials сохраняются{% elif awg3_runtime.known and not awg3_runtime.ready %}Runtime требует восстановления в Maintenance{% else %}AWG 3.0 userspace · конфигурация и QR{% endif %}</small></span>
      </label>"""
new_client_edit = """      {% set awg3_selected = 'amneziawg3' in primary_tokens %}
      <label class=\"dv16-protocol\">
        <input type=\"checkbox\" name=\"protocols\" value=\"amneziawg3\" {% if awg3_selected %}checked{% endif %}>
        <span><strong>AmneziaWG 3.0</strong><small>{{ 'Подключён — существующие credentials сохраняются' if awg3_selected else 'AWG 3.0 userspace · конфигурация и QR' }}</small></span>
      </label>"""
old_device_edit = """      {% set device_awg3_selected = 'amneziawg3' in selected_tokens %}
      <label class=\"dv16-protocol {{ 'is-locked' if awg3_runtime.known and not awg3_runtime.ready and not device_awg3_selected else '' }}\">
        <input type=\"checkbox\" name=\"protocols\" value=\"amneziawg3\" {% if device_awg3_selected %}checked{% endif %} {% if awg3_runtime.known and not awg3_runtime.ready and not device_awg3_selected %}disabled{% endif %}>
        <span><strong>AmneziaWG 3.0</strong><small>{% if device_awg3_selected %}Подключён — существующие credentials сохраняются{% elif awg3_runtime.known and not awg3_runtime.ready %}Runtime требует восстановления в Maintenance{% else %}AWG 3.0 userspace · конфигурация и QR{% endif %}</small></span>
      </label>"""
new_device_edit = """      {% set device_awg3_selected = 'amneziawg3' in selected_tokens %}
      <label class=\"dv16-protocol\">
        <input type=\"checkbox\" name=\"protocols\" value=\"amneziawg3\" {% if device_awg3_selected %}checked{% endif %}>
        <span><strong>AmneziaWG 3.0</strong><small>{{ 'Подключён — существующие credentials сохраняются' if device_awg3_selected else 'AWG 3.0 userspace · конфигурация и QR' }}</small></span>
      </label>"""
for old, new, label in (
    (old_client_edit, new_client_edit, "client edit"),
    (old_device_edit, new_device_edit, "device edit"),
):
    if edits.count(old) != 1:
        raise SystemExit(
            f"expected one gated AWG3.0 {label} card, found {edits.count(old)}"
        )
    edits = edits.replace(old, new)
if edits.count(runtime_set) != 1:
    raise SystemExit(
        f"expected one AWG3.0 runtime set in edit dialogs, found {edits.count(runtime_set)}"
    )
edits = edits.replace(runtime_set, "")
edits_path.write_text(edits, encoding="utf-8")

guard_path = Path(".github/workflows/dev-02206-guard.yml")
guard = guard_path.read_text(encoding="utf-8")
old_select = """          if [[ -f vendor/cores/amneziawg-tools-3.1.20260812.tar.gz ]]; then
            TOOLS=\"vendor/cores/amneziawg-tools-3.1.20260812.tar.gz\"
            GO=\"vendor/cores/amneziawg-go-linux-amd64-v3.1.20260814\"
            EXPECTED_TOOLS_VERSION=\"3.1.20260812\"
          else
            TOOLS=\"vendor/cores/amneziawg-tools-3.0.20260805.tar.gz\"
            GO=\"vendor/cores/amneziawg-go-linux-amd64-v3.0.0\"
            EXPECTED_TOOLS_VERSION=\"3.0.20260805\"
          fi"""
new_select = """          TOOLS=\"vendor/cores/amneziawg-tools-3.0.20260805.tar.gz\"
          GO=\"vendor/cores/amneziawg-go-linux-amd64-v3.0.0\"
          EXPECTED_TOOLS_VERSION=\"3.0.20260805\""" 
focused_anchor = """            tests/test_sg_gateway_v22_awg3_runtime_repair.py \\
            tests/test_sg_gateway_v22_runtime_contract_data_backup.py \\"""
focused_replacement = """            tests/test_sg_gateway_v22_awg3_runtime_repair.py \\
            tests/test_sg_gateway_v22_awg30_first_client_contract.py \\
            tests/test_sg_gateway_v22_runtime_contract_data_backup.py \\"""
if guard.count(old_select) != 1:
    raise SystemExit(
        f"expected one conditional AWG runtime selector, found {guard.count(old_select)}"
    )
if guard.count(focused_anchor) != 1:
    raise SystemExit(f"expected one focused-test anchor, found {guard.count(focused_anchor)}")
guard = guard.replace(old_select, new_select)
guard = guard.replace(focused_anchor, focused_replacement)
guard_path.write_text(guard, encoding="utf-8")
