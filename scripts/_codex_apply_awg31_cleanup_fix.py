from pathlib import Path


def replace_once(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{path}: expected one anchor, found {count}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8", newline="\n")


root = Path("install.sh")
replace_once(
    root,
    '  run_quiet "Этап 10/10 · Проверка команд hostd" stage9_verify_hostd\n  run_quiet "Этап 10/10 · Применение подтверждённого Xray и клиентов" stage9_apply_runtime\n',
    '  run_quiet "Этап 10/10 · Проверка команд hostd" stage9_verify_hostd\n  run_quiet "Этап 10/10 · Подготовка независимого профиля AWG31" run_awg31_stage3a_migration\n  run_quiet "Этап 10/10 · Применение подтверждённого Xray и клиентов" stage9_apply_runtime\n',
)
replace_once(
    root,
    '  run_quiet "Этап 10/10 · Контроль неизменности Clients" verify_client_identities_after_update\n  run_quiet "Этап 10/10 · Независимый профиль AWG31" run_awg31_stage3a_migration\n',
    '  run_quiet "Этап 10/10 · Контроль неизменности Clients" verify_client_identities_after_update\n',
)

deploy = Path("deploy/install-core.sh")
stage3a = '''run_awg31_stage3a_migration() {
  local python="$PREFIX/.venv/bin/python"
  [[ -x "$python" ]] || {
    echo "AWG31 Stage3A requires the installed SG-Gateway Python" >&2
    return 1
  }
  PYTHONPATH="$PREFIX:$PREFIX/hostd" "$python" \\
    -m app.maintenance.awg31_stage3a migrate \\
    --source-root "$SOURCE_DIR" \\
    --root / \\
    --database "$DATA_DIR/sg-gateway.sqlite"
}

'''
replace_once(deploy, "print_sg_admin_status() {\n", stage3a + "print_sg_admin_status() {\n")
replace_once(
    deploy,
    '  run_quiet "Этап 10/10 · Проверка команд hostd" stage9_verify_hostd\n  run_quiet "Этап 10/10 · Применение подтверждённого Xray и клиентов" stage9_apply_runtime\n',
    '  run_quiet "Этап 10/10 · Проверка команд hostd" stage9_verify_hostd\n  run_quiet "Этап 10/10 · Подготовка независимого профиля AWG31" run_awg31_stage3a_migration\n  run_quiet "Этап 10/10 · Применение подтверждённого Xray и клиентов" stage9_apply_runtime\n',
)

uninstall = Path("deploy/full-uninstall-ubuntu.sh")
replace_once(
    uninstall,
    '''remove_account_and_verify(){
  id sg-gateway >/dev/null 2>&1 && userdel sg-gateway >/dev/null 2>&1 || true
  getent group sg-gateway >/dev/null 2>&1 && groupdel sg-gateway >/dev/null 2>&1 || true
  systemctl daemon-reload
  systemctl reset-failed >/dev/null 2>&1 || true

  local bad=0 path
''',
    '''remove_account_and_verify(){
  if id sg-gateway >/dev/null 2>&1; then
    pkill -TERM -u sg-gateway >/dev/null 2>&1 || true
    sleep 1
    pkill -KILL -u sg-gateway >/dev/null 2>&1 || true
    userdel sg-gateway >/dev/null 2>&1 || true
  fi
  getent group sg-gateway >/dev/null 2>&1 && groupdel sg-gateway >/dev/null 2>&1 || true

  # userdel/NSS hooks may touch the former service home after the main
  # state-removal stage. Remove owned paths one final time before the
  # absence checks so Full Uninstall is deterministic and idempotent.
  rm -rf "$PREFIX" "$CONFIG_DIR" "$DATA_DIR" "$LOG_DIR" /run/sg-gateway

  systemctl daemon-reload
  systemctl reset-failed >/dev/null 2>&1 || true

  local bad=0 path
  if id sg-gateway >/dev/null 2>&1; then
    echo "Остаток после удаления: пользователь sg-gateway" >&2
    bad=1
  fi
  if getent group sg-gateway >/dev/null 2>&1; then
    echo "Остаток после удаления: группа sg-gateway" >&2
    bad=1
  fi
''',
)
