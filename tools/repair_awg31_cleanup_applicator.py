from pathlib import Path

path = Path("tools/apply_awg31_only_cleanup.py")
body = path.read_text(encoding="utf-8")

old = "body = replace_once(body, '    awg_private=\"$(awg genkey)\"\\n    awg_public=\"$(printf \\\'%s\\\\n\\\' \"$awg_private\" | awg pubkey)\"\\n', \"\", \"AWG2 keygen\")"
new = "keygen = '    awg_private=\"$(awg genkey)\"\\n    awg_public=\"$(printf \\\'%s\\\\n\\\' \"$awg_private\" | awg pubkey)\"\\n'\nif body.count(keygen) < 1:\n    raise SystemExit(\"AWG2 keygen: no matches\")\nbody = body.replace(keygen, \"\")"
if old not in body:
    raise SystemExit("target applicator keygen line not found")
body = body.replace(old, new, 1)

start_marker = '# Renumber the visible master and drop the two retired runtime stages.\n'
end_marker = '# Existing installer-stage regression becomes the 22-stage contract.\n'
start = body.index(start_marker)
end = body.index(end_marker, start)
replacement = '''# Renumber the visible master and drop the two retired runtime stages.
main_start = body.index("main() {")
main = body[main_start:]
old_master = ''' + '"""' + '''  printf '\\\\n%s[SG-Gateway]%s Запускаю полный мастер SG-Gateway 0.1.0-022.08 · 24 этапа\\\\n' "$CYAN" "$RESET"
  printf '[SG-Gateway] Технический журнал: %s\\\\n' "$INSTALL_LOG"
  printf '[SG-Gateway] Повторный запуск выполняется на этом же EC2. Домен не обязателен.\\\\n\\\\n'

  run_stage 1 "Подготовка Ubuntu" bootstrap_packages
  run_interactive_stage 2 "Определение режима и параметров" stage_prepare_install_context
  run_stage 3 "Проверка установочного комплекта" stage_vendor_media_contract
  run_stage 4 "Резервная копия и исходник" stage_backup_and_prepare
  run_stage 5 "Системные пакеты, Nginx и Certbot" stage_system_packages_02208
  run_stage 6 "AmneziaWG 2 runtime" stage_awg2_runtime
  run_stage 7 "AmneziaWG 3 runtime" stage_awg3_runtime
  run_stage 8 "Xray runtime" stage_xray_runtime
  run_stage 9 "Mihomo runtime" stage_mihomo_runtime
  run_stage 10 "sing-box и WARP runtime" stage_singbox_and_warp_runtime
  run_stage 11 "NaiveProxy runtime" stage_naiveproxy_runtime
  run_stage 12 "Python-окружение и исходник" stage_python_and_source_check
  run_stage 13 "Конфигурация и база" stage_configuration_and_database_02208
  run_stage 14 "Локальная проверка страниц" stage_local_application_smoke_test
  run_stage 15 "Systemd-службы и Nginx" stage_systemd_units_02208
  run_stage 16 "Firewall и сетевые порты" stage_firewall_and_network_02208
  run_stage 17 "Запуск sg-hostd" stage9_start_hostd
  run_stage 18 "Проверка команд hostd" stage9_verify_hostd
  run_stage 19 "Независимый профиль AWG31" run_awg31_stage3a_migration
  run_stage 20 "Применение Xray и клиентов" stage9_apply_runtime
  run_stage 21 "Запуск панели" stage9_start_panel
  run_stage 22 "Проверка Nginx и служб" stage9_verify_nginx
  run_stage 23 "Проверка NaiveProxy" verify_naiveproxy_install_contract
  run_stage 24 "Финальный контракт 22.08" stage_final_contract''' + '"""' + '''
new_master = ''' + '"""' + '''  printf '\\\\n%s[SG-Gateway]%s Запускаю полный мастер SG-Gateway 0.1.0-022.08 · 22 этапа\\\\n' "$CYAN" "$RESET"
  printf '[SG-Gateway] Технический журнал: %s\\\\n' "$INSTALL_LOG"
  printf '[SG-Gateway] Повторный запуск выполняется на этом же EC2. Домен не обязателен.\\\\n\\\\n'

  run_stage 1 "Подготовка Ubuntu" bootstrap_packages
  run_interactive_stage 2 "Определение режима и параметров" stage_prepare_install_context
  run_stage 3 "Проверка установочного комплекта" stage_vendor_media_contract
  run_stage 4 "Резервная копия и исходник" stage_backup_and_prepare
  run_stage 5 "Системные пакеты, Nginx и Certbot" stage_system_packages_02208
  run_stage 6 "Xray runtime" stage_xray_runtime
  run_stage 7 "Mihomo runtime" stage_mihomo_runtime
  run_stage 8 "sing-box и WARP runtime" stage_singbox_and_warp_runtime
  run_stage 9 "NaiveProxy runtime" stage_naiveproxy_runtime
  run_stage 10 "Python-окружение и исходник" stage_python_and_source_check
  run_stage 11 "Конфигурация и база" stage_configuration_and_database_02208
  run_stage 12 "Локальная проверка страниц" stage_local_application_smoke_test
  run_stage 13 "Systemd-службы и Nginx" stage_systemd_units_02208
  run_stage 14 "Firewall и сетевые порты" stage_firewall_and_network_02208
  run_stage 15 "Запуск sg-hostd" stage9_start_hostd
  run_stage 16 "Проверка команд hostd" stage9_verify_hostd
  run_stage 17 "Независимый профиль AWG31" run_awg31_stage3a_migration
  run_stage 18 "Применение Xray и клиентов" stage9_apply_runtime
  run_stage 19 "Запуск панели" stage9_start_panel
  run_stage 20 "Проверка Nginx и служб" stage9_verify_nginx
  run_stage 21 "Проверка NaiveProxy" verify_naiveproxy_install_contract
  run_stage 22 "Финальный контракт 22.08" stage_final_contract''' + '"""' + '''
if old_master not in main:
    raise SystemExit("master stage block: exact current block not found")
main = main.replace(old_master, new_master, 1)
main = main.replace("24/24 · NaiveProxy включён в основной мастер", "22/22 · NaiveProxy включён в основной мастер")
body = body[:main_start] + main
write(path, body)

'''
body = body[:start] + replacement + body[end:]

path.write_text(body, encoding="utf-8", newline="\n")
print("applicator repaired")
