from __future__ import annotations

from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    target = Path(path)
    text = target.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{path}: expected one match, found {count}: {old[:80]!r}")
    target.write_text(text.replace(old, new, 1), encoding="utf-8")


replace_once(
    "app/main.py",
    "from app.connections.settings import get_connection_settings, update_connection_settings\n",
    "from app.connections.settings import get_connection_settings, update_connection_settings\n"
    "from app.connections.awg_dns import (\n"
    "    SharedAwgDnsError,\n"
    "    get_shared_awg_dns,\n"
    "    set_shared_awg_dns,\n"
    ")\n",
)
replace_once(
    "app/main.py",
    '            awg3_settings=get_connection_settings("amneziawg3"),\n',
    '            awg3_settings=get_connection_settings("amneziawg3"),\n'
    '            awg_dns=get_shared_awg_dns(),\n',
)
replace_once(
    "app/main.py",
    '    @app.post("/connections/amneziawg")\n',
    '    @app.post("/connections/awg-dns")\n'
    '    def update_awg_dns():\n'
    '        try:\n'
    '            state = set_shared_awg_dns(request.form.get("dns", ""))\n'
    '        except SharedAwgDnsError as exc:\n'
    '            flash(f"DNS клиентов AWG не сохранён: {exc}", "error")\n'
    '        else:\n'
    '            flash(f"DNS {state.dns} применён к AWG 2.0, 3.0 и 3.1.", "success")\n'
    '        return redirect(url_for("connections") + "#awg-dns")\n\n'
    '    @app.post("/connections/amneziawg")\n',
)

replace_once(
    "app/web/templates/connections.html",
    '            <div class="cnv1-endpoint-main"><img src="{{ country_flag_url(awg_country) }}" alt="{{ country_name(awg_country) }}" width="30" height="20"><div><span>ВНЕШНЯЯ ТОЧКА</span><strong>{{ awg_public_host }}</strong><small>UDP {{ awg_settings.port }} · {{ country_name(awg_country) }}</small></div></div>\n'
    '            <span class="cnv1-port-chip">UDP {{ awg_settings.port }}</span>\n',
    '            <div class="cnv1-endpoint-main"><img src="{{ country_flag_url(awg_country) }}" alt="{{ country_name(awg_country) }}" width="30" height="20"><div><span>ВНЕШНЯЯ ТОЧКА</span><strong>{{ awg_public_host }}:{{ awg_settings.port }} · DNS {{ awg_dns.dns }}</strong><small>{{ country_name(awg_country) }}</small></div></div>\n',
)
replace_once(
    "app/web/templates/connections.html",
    '          <form method="post" action="{{ url_for(\'update_amneziawg\') }}" class="cnv1-engine-form cnv1-engine-form-compact">\n',
    '          <form method="post" action="{{ url_for(\'update_amneziawg\') }}" class="cnv1-engine-form cnv1-engine-form-compact awgd-legacy-settings" hidden>\n',
)
replace_once(
    "app/web/templates/connections.html",
    '            <div class="cnv1-endpoint-main"><img src="{{ country_flag_url(awg3_country) }}" alt="{{ country_name(awg3_country) }}" width="30" height="20"><div><span>ВНЕШНЯЯ ТОЧКА</span><strong>{{ awg3_public_host }}</strong><small>UDP {{ awg3_settings.port }} · {{ country_name(awg3_country) }}</small></div></div>\n'
    '            <span class="cnv1-port-chip">UDP {{ awg3_settings.port }}</span>\n',
    '            <div class="cnv1-endpoint-main"><img src="{{ country_flag_url(awg3_country) }}" alt="{{ country_name(awg3_country) }}" width="30" height="20"><div><span>ВНЕШНЯЯ ТОЧКА</span><strong>{{ awg3_public_host }}:{{ awg3_settings.port }} · DNS {{ awg_dns.dns }}</strong><small>{{ country_name(awg3_country) }}</small></div></div>\n',
)
replace_once(
    "app/web/templates/connections.html",
    '          <form method="post" action="{{ url_for(\'update_amneziawg3\') }}" class="cnv1-engine-form cnv1-engine-form-compact">\n',
    '          <form method="post" action="{{ url_for(\'update_amneziawg3\') }}" class="cnv1-engine-form cnv1-engine-form-compact awgd-legacy-settings" hidden>\n',
)
replace_once(
    "app/web/templates/connections.html",
    '        {% include "_awg31_panel.html" %}\n'
    '      </div>\n'
    '    </article>\n',
    '        {% include "_awg31_panel.html" %}\n'
    '      </div>\n\n'
    '      <section id="awg-dns" class="awgd-shared-dns sg-ljd-nested">\n'
    '        <div class="awgd-shared-dns-copy">\n'
    '          <span>ОБЩАЯ НАСТРОЙКА</span>\n'
    '          <strong>DNS клиентов AWG</strong>\n'
    '          <small>Используется устройствами при активном VPN. Сохранение обновит AWG 2.0, 3.0, 3.1 и существующие клиентские конфигурации.</small>\n'
    '        </div>\n'
    '        <form method="post" action="{{ url_for(\'update_awg_dns\') }}" class="awgd-shared-dns-form">\n'
    '          <label><span>DNS</span><input type="text" name="dns" value="{{ awg_dns.dns }}" inputmode="decimal" autocomplete="off" required></label>\n'
    '          <button class="button primary" type="submit">Сохранить DNS</button>\n'
    '        </form>\n'
    '        {% if not awg_dns.consistent %}<p class="awgd-shared-dns-warning">В профилях сохранены разные DNS. Нажмите «Сохранить DNS», чтобы синхронизировать их.</p>{% endif %}\n'
    '      </section>\n'
    '    </article>\n',
)

replace_once(
    "app/web/templates/_awg31_panel.html",
    '        <strong>{{ awg31_public_host }}</strong>\n'
    '        <small>UDP 587 · {{ country_name(awg3_country) }}</small>\n'
    '        <small class="awgd-v31-technical" hidden>UDP 587 · интерфейс awg31 · 10.131.0.0/24</small>\n',
    '        <strong>{{ awg31_public_host }}:587 · DNS {{ awg_dns.dns }}</strong>\n'
    '        <small>{{ country_name(awg3_country) }}</small>\n'
    '        <small class="awgd-v31-technical" hidden>UDP 587 · интерфейс awg31 · 10.131.0.0/24</small>\n',
)
replace_once(
    "app/web/templates/_awg31_panel.html",
    '    <span class="cnv1-port-chip">UDP 587</span>\n',
    '',
)
replace_once(
    "app/web/templates/_awg31_panel.html",
    '  <form method="post" action="/connections/amneziawg31" class="cnv1-engine-form cnv1-engine-form-compact awgd-v31-form">\n',
    '  <form method="post" action="/connections/amneziawg31" class="cnv1-engine-form cnv1-engine-form-compact awgd-v31-form" hidden>\n',
)

replace_once(
    "app/connections/awg31.py",
    'def _storage_config(\n'
    '    parameters: Mapping[str, str | int],\n'
    '    server_public_key: str = "",\n'
    '    header_protection_key: str = "",\n'
    ') -> dict:\n',
    'def _storage_config(\n'
    '    parameters: Mapping[str, str | int],\n'
    '    server_public_key: str = "",\n'
    '    header_protection_key: str = "",\n'
    '    dns: str = DNS,\n'
    ') -> dict:\n',
)
replace_once(
    "app/connections/awg31.py",
    '        "dns": DNS,\n',
    '        "dns": dns,\n',
)
replace_once(
    "app/connections/awg31.py",
    '        port=int(row["port"] or PORT),\n'
    '    )\n\n\n'
    'def _update_storage(parameters: Mapping[str, str | int], server_public_key: str, header_key: str) -> None:\n'
    '    config = _storage_config(parameters, server_public_key, header_key)\n',
    '        port=int(row["port"] or PORT),\n'
    '        dns=str(config.get("dns") or DNS),\n'
    '    )\n\n\n'
    'def _update_storage(\n'
    '    parameters: Mapping[str, str | int],\n'
    '    server_public_key: str,\n'
    '    header_key: str,\n'
    '    dns: str = DNS,\n'
    ') -> None:\n'
    '    config = _storage_config(parameters, server_public_key, header_key, dns)\n',
)
replace_once(
    "app/connections/awg31.py",
    '    _update_storage(parameters, current.server_public_key, current.header_protection_key)\n',
    '    _update_storage(\n'
    '        parameters, current.server_public_key, current.header_protection_key, current.dns\n'
    '    )\n',
)
replace_once(
    "app/connections/awg31.py",
    '    _update_storage(current.parameters, str(value or "").strip(), current.header_protection_key)\n',
    '    _update_storage(\n'
    '        current.parameters,\n'
    '        str(value or "").strip(),\n'
    '        current.header_protection_key,\n'
    '        current.dns,\n'
    '    )\n',
)
replace_once(
    "app/connections/awg31.py",
    '    _update_storage(parameters, current.server_public_key, key)\n',
    '    _update_storage(parameters, current.server_public_key, key, current.dns)\n',
)

replace_once(
    "app/web/static/sg-awg-dual-v1.css",
    '.page-connections .awgd-v31-service[hidden],\n'
    '.page-connections .awgd-v31-technical[hidden] { display: none !important; }\n',
    '.page-connections .awgd-v31-service[hidden],\n'
    '.page-connections .awgd-v31-technical[hidden],\n'
    '.page-connections .awgd-legacy-settings[hidden],\n'
    '.page-connections .awgd-v31-form[hidden] { display: none !important; }\n'
    '.page-connections .awgd-shared-dns {\n'
    '  display: grid;\n'
    '  grid-template-columns: minmax(0, 1fr) auto;\n'
    '  align-items: end;\n'
    '  gap: 18px;\n'
    '  margin: 0 18px 18px;\n'
    '  padding: 14px 16px;\n'
    '}\n'
    '.page-connections .awgd-shared-dns-copy > span { display: block; color: var(--sg-green); font-size: 9px; font-weight: 900; letter-spacing: .08em; }\n'
    '.page-connections .awgd-shared-dns-copy > strong { display: block; margin-top: 4px; color: var(--sg-text); font-size: 14px; }\n'
    '.page-connections .awgd-shared-dns-copy > small { display: block; max-width: 720px; margin-top: 4px; color: var(--sg-muted); font-size: 10px; line-height: 1.45; }\n'
    '.page-connections .awgd-shared-dns-form { display: grid; grid-template-columns: minmax(210px, 300px) auto; align-items: end; gap: 10px; }\n'
    '.page-connections .awgd-shared-dns-form label { margin: 0; }\n'
    '.page-connections .awgd-shared-dns-form label > span { display: block; margin-bottom: 6px; color: var(--sg-muted); font-size: 9px; font-weight: 800; text-transform: uppercase; }\n'
    '.page-connections .awgd-shared-dns-form input { min-height: 38px; }\n'
    '.page-connections .awgd-shared-dns-form .button { min-height: 38px; white-space: nowrap; }\n'
    '.page-connections .awgd-shared-dns-warning { grid-column: 1 / -1; margin: -4px 0 0; color: var(--sg-warning); font-size: 10px; }\n',
)
replace_once(
    "app/web/static/sg-awg-dual-v1.css",
    '@media (max-width: 820px) {\n'
    '  .page-connections .awgd-grid { grid-template-columns: 1fr; }\n',
    '@media (max-width: 820px) {\n'
    '  .page-connections .awgd-grid { grid-template-columns: 1fr; }\n'
    '  .page-connections .awgd-shared-dns { grid-template-columns: 1fr; }\n'
    '  .page-connections .awgd-shared-dns-form { grid-template-columns: minmax(0, 1fr) auto; }\n',
)
replace_once(
    "app/web/static/sg-awg-dual-v1.css",
    '  .page-connections .awgd-card .cnv1-endpoint-card,\n'
    '  .page-connections .awgd-v31-service { margin-inline: 12px; }\n',
    '  .page-connections .awgd-card .cnv1-endpoint-card,\n'
    '  .page-connections .awgd-v31-service { margin-inline: 12px; }\n'
    '  .page-connections .awgd-shared-dns { margin-inline: 12px; }\n'
    '  .page-connections .awgd-shared-dns-form { grid-template-columns: 1fr; }\n',
)

print("AWG shared DNS UI patch applied")
