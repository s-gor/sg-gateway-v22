from __future__ import annotations

from pathlib import Path


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"expected one {label}, found {count}")
    return text.replace(old, new)


runtime_set = "{% set awg3_runtime = runtime_engine_state('amneziawg3') if runtime_engine_state is defined else {'known': false, 'ready': true, 'missing': []} %}\n"

clients_path = Path("app/web/templates/clients.html")
clients = clients_path.read_text(encoding="utf-8")
clients = replace_once(
    clients,
    "<label class=\"cv10-protocol {{ 'is-locked' if awg3_runtime.known and not awg3_runtime.ready else '' }}\">",
    "<label class=\"cv10-protocol\">",
    "gated AWG3.0 create label",
)
clients = replace_once(
    clients,
    "<input type=\"checkbox\" name=\"protocols\" value=\"amneziawg3\" {% if awg3_runtime.known and not awg3_runtime.ready %}disabled{% endif %}>",
    "<input type=\"checkbox\" name=\"protocols\" value=\"amneziawg3\">",
    "disabled AWG3.0 create input",
)
clients = replace_once(
    clients,
    "<small>{{ 'AWG3 runtime требует восстановления в Maintenance' if awg3_runtime.known and not awg3_runtime.ready else 'AWG 3.0 userspace · отдельная конфигурация и QR' }}</small>",
    "<small>AWG 3.0 userspace · отдельная конфигурация и QR</small>",
    "conditional AWG3.0 create note",
)
warning = """    {% if awg3_runtime.known and not awg3_runtime.ready %}
    <div class=\"cv2-filter-footer\" data-awg3-runtime-warning>
      AWG3 временно недоступен. <a href=\"{{ url_for('maintenance', tab='updates') }}\">Открыть Maintenance → AWG3 Runtime</a>.
    </div>
    {% endif %}
"""
clients = replace_once(clients, warning, "", "blocking AWG3.0 runtime warning")
clients = replace_once(clients, runtime_set, "", "AWG3.0 runtime set in create dialog")
clients_path.write_text(clients, encoding="utf-8")

edits_path = Path("app/web/templates/_client_edit_dialogs.html")
edits = edits_path.read_text(encoding="utf-8")
edits = replace_once(
    edits,
    "<label class=\"dv16-protocol {{ 'is-locked' if awg3_runtime.known and not awg3_runtime.ready and not awg3_selected else '' }}\">",
    "<label class=\"dv16-protocol\">",
    "gated AWG3.0 client-edit label",
)
edits = replace_once(
    edits,
    "<input type=\"checkbox\" name=\"protocols\" value=\"amneziawg3\" {% if awg3_selected %}checked{% endif %} {% if awg3_runtime.known and not awg3_runtime.ready and not awg3_selected %}disabled{% endif %}>",
    "<input type=\"checkbox\" name=\"protocols\" value=\"amneziawg3\" {% if awg3_selected %}checked{% endif %}>",
    "disabled AWG3.0 client-edit input",
)
edits = replace_once(
    edits,
    "<small>{% if awg3_selected %}Подключён — существующие credentials сохраняются{% elif awg3_runtime.known and not awg3_runtime.ready %}Runtime требует восстановления в Maintenance{% else %}AWG 3.0 userspace · конфигурация и QR{% endif %}</small>",
    "<small>{{ 'Подключён — существующие credentials сохраняются' if awg3_selected else 'AWG 3.0 userspace · конфигурация и QR' }}</small>",
    "conditional AWG3.0 client-edit note",
)
edits = replace_once(
    edits,
    "<label class=\"dv16-protocol {{ 'is-locked' if awg3_runtime.known and not awg3_runtime.ready and not device_awg3_selected else '' }}\">",
    "<label class=\"dv16-protocol\">",
    "gated AWG3.0 device-edit label",
)
edits = replace_once(
    edits,
    "<input type=\"checkbox\" name=\"protocols\" value=\"amneziawg3\" {% if device_awg3_selected %}checked{% endif %} {% if awg3_runtime.known and not awg3_runtime.ready and not device_awg3_selected %}disabled{% endif %}>",
    "<input type=\"checkbox\" name=\"protocols\" value=\"amneziawg3\" {% if device_awg3_selected %}checked{% endif %}>",
    "disabled AWG3.0 device-edit input",
)
edits = replace_once(
    edits,
    "<small>{% if device_awg3_selected %}Подключён — существующие credentials сохраняются{% elif awg3_runtime.known and not awg3_runtime.ready %}Runtime требует восстановления в Maintenance{% else %}AWG 3.0 userspace · конфигурация и QR{% endif %}</small>",
    "<small>{{ 'Подключён — существующие credentials сохраняются' if device_awg3_selected else 'AWG 3.0 userspace · конфигурация и QR' }}</small>",
    "conditional AWG3.0 device-edit note",
)
edits = replace_once(edits, runtime_set, "", "AWG3.0 runtime set in edit dialogs")
edits_path.write_text(edits, encoding="utf-8")

guard_path = Path(".github/workflows/dev-02206-guard.yml")
guard = guard_path.read_text(encoding="utf-8")
old_selector = """          if [[ -f vendor/cores/amneziawg-tools-3.1.20260812.tar.gz ]]; then
            TOOLS=\"vendor/cores/amneziawg-tools-3.1.20260812.tar.gz\"
            GO=\"vendor/cores/amneziawg-go-linux-amd64-v3.1.20260814\"
            EXPECTED_TOOLS_VERSION=\"3.1.20260812\"
          else
            TOOLS=\"vendor/cores/amneziawg-tools-3.0.20260805.tar.gz\"
            GO=\"vendor/cores/amneziawg-go-linux-amd64-v3.0.0\"
            EXPECTED_TOOLS_VERSION=\"3.0.20260805\"
          fi"""
new_selector = """          TOOLS=\"vendor/cores/amneziawg-tools-3.0.20260805.tar.gz\"
          GO=\"vendor/cores/amneziawg-go-linux-amd64-v3.0.0\"
          EXPECTED_TOOLS_VERSION=\"3.0.20260805\""" 
guard = replace_once(guard, old_selector, new_selector, "conditional AWG runtime selector")
backslash = chr(92)
anchor = "            tests/test_sg_gateway_v22_awg3_runtime_repair.py " + backslash + "\n"
addition = anchor + "            tests/test_sg_gateway_v22_awg30_first_client_contract.py " + backslash + "\n"
guard = replace_once(guard, anchor, addition, "focused AWG3.0 test anchor")
guard_path.write_text(guard, encoding="utf-8")
