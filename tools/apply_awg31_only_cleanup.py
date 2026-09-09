from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def write(path: str, body: str) -> None:
    (ROOT / path).write_text(body, encoding="utf-8", newline="\n")


def replace_once(body: str, old: str, new: str, label: str) -> str:
    count = body.count(old)
    if count != 1:
        raise SystemExit(f"{label}: expected one match, got {count}")
    return body.replace(old, new, 1)


def sub_once(body: str, pattern: str, replacement: str, label: str, flags: int = 0) -> str:
    body, count = re.subn(pattern, replacement, body, count=1, flags=flags)
    if count != 1:
        raise SystemExit(f"{label}: expected one match, got {count}")
    return body


# Connections template: use the canonical [AWG31, Xray, Mihomo] summary order and
# replace the historical three-generation showcase with one current AWG31 card.
path = "app/web/templates/connections.html"
body = read(path)
body = sub_once(
    body,
    r"\{% set awg_key_ready = .*?\{% set awg31_public_host = awg3_public_host %\}\n",
    "{% set xray_key_ready = xray_settings.enabled and xray_settings.config.get('public_key', '') and 'PLACEHOLDER' not in xray_settings.config.get('public_key', '') %}\n"
    "{% set xray_short_ready = xray_settings.config.get('short_id', '') and 'PLACEHOLDER' not in xray_settings.config.get('short_id', '') %}\n"
    "{% set xray_ready = xray_key_ready and xray_short_ready %}\n"
    "{% set awg31_country = connections[0].country_code if connections else 'unknown' %}\n"
    "{% set xray_country = connections[1].country_code if connections | length > 1 else 'unknown' %}\n"
    "{% set awg31_public_host = connections[0].public_host if connections else 'awg31.internal' %}\n"
    "{% set xray_public_host = connections[1].public_host if connections | length > 1 else xray_settings.host %}\n"
    "{% set mihomo_public_host = connections[2].public_host if connections | length > 2 else mihomo.settings.host %}\n",
    "connections context",
    flags=re.S,
)
body = replace_once(
    body,
    "<p>AmneziaWG 2 / 3, четыре независимых Xray-профиля и Mihomo.</p>",
    "<p>AmneziaWG 3.1, четыре независимых Xray-профиля, Mihomo и NaiveProxy.</p>",
    "connections intro",
)
start = body.index('    <article class="cnv1-engine-card cnv1-engine-awg awgd-shell sg-ljd-card">')
end = body.index('    {% include "_mihomo_panel.html" %}', start)
awg_block = '''    <article class="cnv1-engine-card cnv1-engine-awg awgd-shell sg-ljd-card sg-ui-card sg-ui-section">
      <header class="cnv1-engine-head">
        <div class="cnv1-engine-title">
          <div class="cnv1-engine-logo awg"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M3 12h4l2-7 4 14 2-7h6"/></svg></div>
          <div>
            <div class="cnv1-card-kicker">UDP VPN · AWG3.1</div>
            <h2>AmneziaWG 3.1</h2>
            <p>Один актуальный AWG-профиль с независимым userspace runtime.</p>
          </div>
        </div>
      </header>

      <div class="awgd-inner-rail sg-ui-rail">
        {% include "_awg31_panel.html" %}

        <section id="awg-dns" class="awgd-shared-dns sg-ljd-nested sg-ui-nested">
          <div class="awgd-shared-dns-copy">
            <span>НАСТРОЙКА</span>
            <strong>DNS клиентов AWG3.1</strong>
            <small>Используется устройствами при активном AWG3.1. Сохранение обновит существующие клиентские конфигурации AWG3.1.</small>
          </div>
          <form method="post" action="{{ url_for('update_awg_dns') }}" class="awgd-shared-dns-form">
            <label><span>DNS</span><input type="text" name="dns" value="{{ awg_dns.dns }}" autocomplete="off" required></label>
            <button class="button primary" type="submit">Сохранить DNS</button>
          </form>
          {% if not awg_dns.consistent %}<p class="awgd-shared-dns-warning">DNS AWG3.1 требует синхронизации. Нажмите «Сохранить DNS».</p>{% endif %}
        </section>
      </div>
    </article>

'''
body = body[:start] + awg_block + body[end:]
write(path, body)

# AWG31 panel must use AWG31's own country, never AWG3.0 fallback state.
path = "app/web/templates/_awg31_panel.html"
body = read(path).replace("awg3_country", "awg31_country")
write(path, body)

# Sidebar copy.
path = "app/web/templates/base.html"
body = replace_once(read(path), "AWG2/3 · Xray · Mihomo", "AWG3.1 · Xray · Mihomo", "sidebar")
write(path, body)

# Backend: stop querying/recreating retired connections from the live Connections page.
path = "app/main.py"
body = read(path)
body = replace_once(
    body,
    '            awg_settings=get_connection_settings("amneziawg"),\n            awg3_settings=get_connection_settings("amneziawg3"),\n',
    "",
    "retired connection context",
)
body = replace_once(
    body,
    '            flash(f"DNS {state.dns} применён к AWG 2.0, 3.0 и 3.1.", "success")',
    '            flash(f"DNS {state.dns} применён к AWG3.1.", "success")',
    "AWG DNS flash",
)
body = sub_once(
    body,
    r'\n    @app\.post\("/connections/amneziawg"\).*?(?=\n    @app\.post\("/connections/xray"\))',
    "\n",
    "retired connection endpoints",
    flags=re.S,
)
write(path, body)

# Installer: 22 visible stages, no active AWG2/AWG3 install/seed/unit/firewall path.
path = "install.sh"
body = read(path)
body = replace_once(body, "TOTAL_STAGES=24", "TOTAL_STAGES=22", "stage count")
body = replace_once(body, '    awg_private="$(awg genkey)"\n    awg_public="$(printf \'%s\\n\' "$awg_private" | awg pubkey)"\n', "", "AWG2 keygen")
body = sub_once(
    body,
    r'\nSG_GATEWAY_AWG_PRIVATE_KEY=\$\{awg_private\}.*?SG_GATEWAY_AWG_H4=\$\{h4\}\n',
    "\n",
    "AWG2 engine secrets",
    flags=re.S,
)
body = replace_once(body, '    SG_SEED_AWG_PORT="$AWG_PORT" \\\n', "", "AWG seed port")
body = replace_once(body, '    SG_SEED_AWG_PUBLIC_KEY="$awg_public" \\\n', "", "AWG seed key")
body = sub_once(
    body,
    r'\n  runuser -u "\$PANEL_USER" -- env \\\n    PYTHONPATH="\$PREFIX" \\\n    SG_GATEWAY_DATA_DIR="\$DATA_DIR" \\\n    "\$PREFIX/\.venv/bin/python" - <<\'PYAWG585\'.*?\nPYAWG585\n',
    "\n",
    "AWG585 invariant",
    flags=re.S,
)
body = replace_once(body, '  install -m 0644 "$PREFIX/deploy/sg-gateway-awg.service" /etc/systemd/system/sg-gateway-awg.service\n', "", "AWG2 unit install")
body = replace_once(body, '  install -m 0644 "$PREFIX/deploy/sg-gateway-awg3.service" /etc/systemd/system/sg-gateway-awg3.service\n', "", "AWG3 unit install")
body = replace_once(
    body,
    '    systemctl disable sg-gateway-awg.service sg-gateway-awg3.service sg-gateway-singbox.service >/dev/null 2>&1 || true',
    '    systemctl disable sg-gateway-singbox.service >/dev/null 2>&1 || true',
    "clean install disable list",
)
body = replace_once(
    body,
    '      "${AWG_PORT}/udp" "${AWG3_PORT}/udp" "${HYSTERIA2_PORT}/udp" \\\n',
    '      "${HYSTERIA2_PORT}/udp" \\\n',
    "firewall old AWG allows",
)
# Remove retired runtime services from successful update restore, but preserve legacy
# snapshot/rollback machinery elsewhere in the file.
restore_start = body.index("restore_update_runtime_services()")
restore_end = body.index("stage9_verify_nginx()", restore_start)
restore = body[restore_start:restore_end]
restore = restore.replace(" sg-gateway-awg.service", "").replace(" sg-gateway-awg3.service", "")
body = body[:restore_start] + restore + body[restore_end:]
# Renumber the visible master and drop the two retired runtime stages.
main_start = body.index("main() {")
main = body[main_start:]
main = sub_once(
    main,
    r'  run_stage 1 "Подготовка Ubuntu" stage_prepare_ubuntu.*?  run_stage 24 "Финальный контракт 22\.08" stage_final_contract',
    '''  run_stage 1 "Подготовка Ubuntu" stage_prepare_ubuntu
  run_stage 2 "Определение режима и параметров" stage_detect_mode_and_parameters
  run_stage 3 "Проверка локальных install-media" stage_verify_install_media
  run_stage 4 "Резервная копия и подготовка" stage_backup_and_prepare
  run_stage 5 "Системные пакеты, Nginx и Certbot" stage_packages_nginx_certbot
  run_stage 6 "Xray runtime" stage_xray_runtime
  run_stage 7 "Mihomo runtime" stage_mihomo_runtime
  run_stage 8 "sing-box и WARP runtime" stage_singbox_warp_runtime
  run_stage 9 "NaiveProxy runtime" stage_naiveproxy_runtime
  run_stage 10 "Python и исходники SG-Gateway" stage_python_and_source
  run_stage 11 "Конфигурация и база данных" stage_configuration_and_database
  run_stage 12 "Локальная проверка страниц" stage_local_application_smoke_test
  run_stage 13 "Systemd и Nginx" stage_systemd_units
  run_stage 14 "Firewall и сеть" stage_firewall_and_network
  run_stage 15 "Запуск HostD" stage_start_hostd
  run_stage 16 "Проверка HostD commands" stage_verify_hostd_commands
  run_stage 17 "Независимый профиль AWG31" run_awg31_stage3a_migration
  run_stage 18 "Xray и клиенты" stage_apply_xray_and_clients
  run_stage 19 "Запуск панели" stage_start_panel
  run_stage 20 "Nginx и сервисы" stage_start_nginx_and_services
  run_stage 21 "Проверка NaiveProxy" verify_naiveproxy_install_contract
  run_stage 22 "Финальный контракт 22.08" stage_final_contract''',
    "master stage block",
    flags=re.S,
)
main = main.replace("24/24 · NaiveProxy включён в основной мастер", "22/22 · NaiveProxy включён в основной мастер")
body = body[:main_start] + main
write(path, body)

# Existing installer-stage regression becomes the 22-stage contract.
path = "tests/test_installer_02208_master_24_stages.py"
body = read(path)
body = body.replace("24", "22")
body = body.replace("master_22_stages", "master_22_stages")
body = body.replace('"AmneziaWG 2 runtime",\n        "AmneziaWG 3 runtime",\n        ', "")
write(path, body)

print("AWG31-only cleanup applied")
