from __future__ import annotations

import re
from pathlib import Path


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"expected one {label}, found {count}")
    return text.replace(old, new)


def sub_once(text: str, pattern: str, replacement: str, label: str) -> str:
    result, count = re.subn(pattern, replacement, text, count=1, flags=re.S)
    if count != 1:
        raise SystemExit(f"expected one {label}, found {count}")
    return result


runtime_set = "{% set awg3_runtime = runtime_engine_state('amneziawg3') if runtime_engine_state is defined else {'known': false, 'ready': true, 'missing': []} %}\n"

clients_path = Path("app/web/templates/clients.html")
clients = clients_path.read_text(encoding="utf-8")
clients = replace_once(clients, "<label class=\"cv10-protocol {{ 'is-locked' if awg3_runtime.known and not awg3_runtime.ready else '' }}\">", "<label class=\"cv10-protocol\">", "gated AWG3.0 create label")
clients = replace_once(clients, "<input type=\"checkbox\" name=\"protocols\" value=\"amneziawg3\" {% if awg3_runtime.known and not awg3_runtime.ready %}disabled{% endif %}>", "<input type=\"checkbox\" name=\"protocols\" value=\"amneziawg3\">", "disabled AWG3.0 create input")
clients = replace_once(clients, "<small>{{ 'AWG3 runtime требует восстановления в Maintenance' if awg3_runtime.known and not awg3_runtime.ready else 'AWG 3.0 userspace · отдельная конфигурация и QR' }}</small>", "<small>AWG 3.0 userspace · отдельная конфигурация и QR</small>", "conditional AWG3.0 create note")
warning_pattern = r"    \{% if awg3_runtime\.known and not awg3_runtime\.ready %\}\n    <div class=\"cv2-filter-footer\" data-awg3-runtime-warning>\n.*?\n    </div>\n    \{% endif %\}\n"
clients = sub_once(clients, warning_pattern, "", "blocking AWG3.0 runtime warning")
clients = replace_once(clients, runtime_set, "", "AWG3.0 runtime set in create dialog")
clients_path.write_text(clients, encoding="utf-8")

edits_path = Path("app/web/templates/_client_edit_dialogs.html")
edits = edits_path.read_text(encoding="utf-8")
edits = replace_once(edits, "<label class=\"dv16-protocol {{ 'is-locked' if awg3_runtime.known and not awg3_runtime.ready and not awg3_selected else '' }}\">", "<label class=\"dv16-protocol\">", "gated AWG3.0 client-edit label")
edits = replace_once(edits, "<input type=\"checkbox\" name=\"protocols\" value=\"amneziawg3\" {% if awg3_selected %}checked{% endif %} {% if awg3_runtime.known and not awg3_runtime.ready and not awg3_selected %}disabled{% endif %}>", "<input type=\"checkbox\" name=\"protocols\" value=\"amneziawg3\" {% if awg3_selected %}checked{% endif %}>", "disabled AWG3.0 client-edit input")
edits = replace_once(edits, "<small>{% if awg3_selected %}Подключён — существующие credentials сохраняются{% elif awg3_runtime.known and not awg3_runtime.ready %}Runtime требует восстановления в Maintenance{% else %}AWG 3.0 userspace · конфигурация и QR{% endif %}</small>", "<small>{{ 'Подключён — существующие credentials сохраняются' if awg3_selected else 'AWG 3.0 userspace · конфигурация и QR' }}</small>", "conditional AWG3.0 client-edit note")
edits = replace_once(edits, "<label class=\"dv16-protocol {{ 'is-locked' if awg3_runtime.known and not awg3_runtime.ready and not device_awg3_selected else '' }}\">", "<label class=\"dv16-protocol\">", "gated AWG3.0 device-edit label")
edits = replace_once(edits, "<input type=\"checkbox\" name=\"protocols\" value=\"amneziawg3\" {% if device_awg3_selected %}checked{% endif %} {% if awg3_runtime.known and not awg3_runtime.ready and not device_awg3_selected %}disabled{% endif %}>", "<input type=\"checkbox\" name=\"protocols\" value=\"amneziawg3\" {% if device_awg3_selected %}checked{% endif %}>", "disabled AWG3.0 device-edit input")
edits = replace_once(edits, "<small>{% if device_awg3_selected %}Подключён — существующие credentials сохраняются{% elif awg3_runtime.known and not awg3_runtime.ready %}Runtime требует восстановления в Maintenance{% else %}AWG 3.0 userspace · конфигурация и QR{% endif %}</small>", "<small>{{ 'Подключён — существующие credentials сохраняются' if device_awg3_selected else 'AWG 3.0 userspace · конфигурация и QR' }}</small>", "conditional AWG3.0 device-edit note")
edits = replace_once(edits, runtime_set, "", "AWG3.0 runtime set in edit dialogs")
edits_path.write_text(edits, encoding="utf-8")
