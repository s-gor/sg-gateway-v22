#!/usr/bin/env bash
set -Eeuo pipefail
# Compatibility acceptance marker: __SG_GATEWAY_02110_BINARY_PAYLOAD_BELOW__

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
OUT="${1:-$ROOT/SG-Gateway-02112-FULL-CLEAN.run}"
SOURCE_FOLDER="SG-Gateway-02112-SOURCE"
EXPECTED_VERSION="0.1.0-021.12"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
STAGE="$TMP/$SOURCE_FOLDER"
PAYLOAD="$TMP/payload.tar.gz"
SHA_FILE="${OUT%.run}-SHA256.txt"
TRANSFER_ZIP="${OUT%.run}-TRANSFER.zip"

mkdir -p "$STAGE"
# SG_GATEWAY_02112_CANONICAL_GIT_ARCHIVE_FIX11
# Inside a Git checkout, build exactly committed HEAD. This removes
# Windows/Linux EOL ambiguity from SOURCE-SHA256SUMS and FULL CLEAN.
if command -v git >/dev/null 2>&1 && git -C "$ROOT" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  git -C "$ROOT" archive --format=tar HEAD | tar -C "$STAGE" -xf -
else
  tar -C "$ROOT" \
  --exclude='./.git' \
  --exclude='./.venv' \
  --exclude='./venv' \
  --exclude='./.pytest_cache' \
  --exclude='./.ruff_cache' \
  --exclude='*/__pycache__' \
  --exclude='*.pyc' \
  --exclude='*.pyo' \
  --exclude='./SG-Gateway-02112-FULL-CLEAN*.run' \
  --exclude='./SG-Gateway-02112-FULL-CLEAN*-TRANSFER.zip' \
  --exclude='./SG-Gateway-02112-FULL-CLEAN*-SHA256.txt' \
  -cf - . | tar -C "$STAGE" -xf -
fi

tar --sort=name --mtime='UTC 2026-08-09' --owner=0 --group=0 --numeric-owner \
  -C "$TMP" -czf "$PAYLOAD" "$SOURCE_FOLDER"
PAYLOAD_SHA="$(sha256sum "$PAYLOAD" | awk '{print $1}')"

cat > "$OUT" <<EOF
#!/usr/bin/env bash
set -Eeuo pipefail

PACKAGE="SG-Gateway 0.1.0-021.12 Full Clean MAIN-02112"
EXPECTED_VERSION="$EXPECTED_VERSION"
SOURCE_FOLDER="$SOURCE_FOLDER"
PAYLOAD_SHA256="$PAYLOAD_SHA"
PAYLOAD_MARKER="__SG_GATEWAY_02112_BINARY_PAYLOAD_BELOW__"
SELF="\$(readlink -f "\${BASH_SOURCE[0]}")"
TEMP_DIR=""

cleanup() { [[ -z "\${TEMP_DIR:-}" || ! -d "\$TEMP_DIR" ]] || rm -rf "\$TEMP_DIR"; }
trap cleanup EXIT INT TERM
fail() { printf '[SG-Gateway] [ERROR] %s\\n' "\$*" >&2; exit 1; }

extract_payload() {
  local command payload actual payload_line
  for command in awk tail sha256sum tar python3 bash readlink mktemp; do
    command -v "\$command" >/dev/null 2>&1 || fail "Не найдена команда: \$command"
  done
  TEMP_DIR="\$(mktemp -d /tmp/sg-gateway-02112.XXXXXX)"
  payload="\$TEMP_DIR/payload.tar.gz"
  payload_line="\$(awk -v marker="\$PAYLOAD_MARKER" '\$0 == marker { print NR + 1; exit }' "\$SELF")"
  [[ "\$payload_line" =~ ^[0-9]+\$ ]] || fail "Не найден встроенный binary payload"
  tail -n "+\$payload_line" "\$SELF" > "\$payload" || fail "Не удалось извлечь встроенный payload"
  actual="\$(sha256sum "\$payload" | awk '{print \$1}')"
  [[ "\$actual" == "\$PAYLOAD_SHA256" ]] || fail "Контрольная сумма payload не совпала"
  tar -xzf "\$payload" -C "\$TEMP_DIR" || fail "Не удалось распаковать payload"
  [[ -d "\$TEMP_DIR/\$SOURCE_FOLDER" ]] || fail "Каталог исходника не извлечён"
}

verify_source() {
  local root shell_file
  root="\$TEMP_DIR/\$SOURCE_FOLDER"
  [[ "\$(tr -d '[:space:]' < "\$root/VERSION")" == "\$EXPECTED_VERSION" ]] || fail "Версия payload не совпала"
  [[ "\$(tr -d '[:space:]' < "\$root/BUILD-ID")" == "MAIN-02112" ]] || fail "Build ID payload не совпал"
  (cd "\$root" && sha256sum -c SOURCE-SHA256SUMS >/dev/null) || fail "Файлы исходника повреждены"
  (cd "\$root/vendor/cores" && sha256sum -c SHA256SUMS >/dev/null) || fail "Vendored engines повреждены"
  while IFS= read -r -d '' shell_file; do
    bash -n "\$shell_file" || fail "Ошибка shell-синтаксиса: \${shell_file#\$root/}"
  done < <(find "\$root" -type f -name '*.sh' -print0)
  [[ "\$(sha256sum "\$root/assets/placeholder/index.html" | awk '{print \$1}')" == "06b280bab43d9ed4ceeb75d34008b60158366a968e6eb950b3e0b4b0cbcdd226" ]] || fail "Заглушка не совпала с принятой"
  grep -Fq 'SG_GATEWAY_02110_HTTPS_VERIFY_RETRY_FIX1' "\$root/deploy/configure-panel-access.sh" || fail "Нет HTTPS retry"
  grep -Fq '/root/sg-gateway-02112-installer-resume.env' "\$root/deploy/full-uninstall-ubuntu.sh" || fail "Uninstall не очищает current resume 02112"
  grep -Fq '/root/sg-gateway-02111-installer-resume.env' "\$root/deploy/full-uninstall-ubuntu.sh" || fail "Uninstall не очищает resume 02111"
  grep -Fq 'include\\s+/etc/nginx/stream-conf\\.d/sg-gateway-443\\.conf' "\$root/deploy/full-uninstall-ubuntu.sh" || fail "Uninstall не очищает direct stream include"
  grep -Fq 'SG_DEVICE_COLLAPSE_V4_LAST_CSS' "\$root/app/web/templates/base.html" || fail "Нет финального Device Collapse V4"
  grep -Fq 'SG_DEVICE_EXPANDED_CLEANUP_V1_LAST_CSS' "\$root/app/web/templates/base.html" || fail "Нет очистки раскрытой карточки устройства"
  grep -Fq 'def recovery_restore_backup_route(name: str):' "\$root/app/main.py" || fail "Нет восстановления из Recovery"
  grep -Fq 'data-recovery-restore' "\$root/app/web/templates/recovery.html" || fail "Нет кнопки восстановления в Recovery"
  grep -Fq 'System alignment final fix 3 — Disk is the reference' "\$root/app/web/static/sg-system-simple-dials-v1.css" || fail "Нет финального System FIX3"
  grep -Fq 'Скопировать ссылку' "\$root/app/web/templates/client_detail.html" || fail "Нет принятой кнопки подписки"
  grep -Fq 'SG_GATEWAY_02110_INSTALLER_SAFETY_FIX2' "\$root/install.sh" || fail "Нет installer safety fix 2"
  grep -Fq 'SG_GATEWAY_02110_SYSTEMD_TRANSIENT_RETRY_FIX3' "\$root/install.sh" || fail "Нет systemd transient retry fix 3"
  grep -Fq 'SG_GATEWAY_02110_UNINSTALL_SAFETY_FIX2' "\$root/deploy/full-uninstall-ubuntu.sh" || fail "Нет uninstall safety fix 2"
  grep -Fq 'def restore_uploaded_full_backup' "\$root/hostd/sg_hostd/full_backup_runtime.py" || fail "Нет Full Backup runtime"
  grep -Fq 'backup.full.restore.start' "\$root/hostd/sg_hostd/commands.py" || fail "Нет фонового Full Restore"
  grep -Fq 'FULL_BACKUP_PANEL_DATA_PERMISSIONS_FIX3' "\$root/hostd/sg_hostd/full_backup_runtime.py" || fail "Нет исправления прав SQLite"
  grep -Fq 'SG_GATEWAY_02111_PORTABLE_RESTORE_V2' "\$root/hostd/sg_hostd/full_backup_runtime.py" || fail "Нет portable restore V2"
  grep -Fq 'SG_GATEWAY_02111_PORTABLE_HOST_REBIND' "\$root/hostd/sg_hostd/full_backup_runtime.py" || fail "Restore не привязывает state к новому IP"
  grep -Fq 'SG_GATEWAY_02111_REGENERATE_RUNTIME_FROM_STATE' "\$root/hostd/sg_hostd/full_backup_runtime.py" || fail "Restore не пересобирает runtime"
  grep -Fq 'portable_runtime_regenerated' "\$root/hostd/sg_hostd/full_backup_runtime.py" || fail "Restore не подтверждает пересборку runtime"
  grep -Fq 'SG_GATEWAY_02111_OPERATION_JOB_PRESERVE_FIX' "\$root/hostd/sg_hostd/full_backup_runtime.py" || fail "Restore может затереть live job log при rollback"
  grep -Fq 'SG_GATEWAY_02111_RESTORE_SESSION_PRESERVE_FIX' "\$root/hostd/sg_hostd/full_backup_runtime.py" || fail "Restore не сохраняет session secret нового сервера"
  grep -Fq '"SG_GATEWAY_SECRET_KEY"' "\$root/hostd/sg_hostd/full_backup_runtime.py" || fail "SG_GATEWAY_SECRET_KEY не сохранён при portable restore"
  grep -Fq 'SG_GATEWAY_02111_RESTORE_HTTPS_BOOTSTRAP_FIX' "\$root/deploy/configure-panel-access.sh" || fail "Нет bootstrap HTTPS из локальных сертификатов"
  grep -Fq 'id="opjob-refresh"' "\$root/app/web/templates/operation_job.html" || fail "Нет кнопки обновления страницы Full Restore"
  grep -Fq 'SG_GATEWAY_02111_RESTORE_RESTART_PAGE_FIX' "\$root/deploy/configure-panel-access.sh" || fail "HTTPS vhost не показывает restart page при backend restart"
  grep -Fq 'SG_GATEWAY_02111_RESTORE_RESTART_PAGE_FIX' "\$root/install.sh" || fail "Initial panel vhost не показывает restart page"
  [[ -f "\$root/assets/placeholder/restarting.html" ]] || fail "Нет статической restart page"
  grep -Fq 'SG_GATEWAY_FULL_BACKUP_UPLOAD_FIX1' "\$root/deploy/configure-panel-access.sh" || fail "Нет upload limit для Full Restore"
  grep -Fq 'SG_GATEWAY_02111_CUMULATIVE_FULL_RESTORE_UPLOAD_FIX' "\$root/install.sh" || fail "Clean/update installer не гарантирует upload limit Full Restore"
  grep -Fq 'client_max_body_size 0;' "\$root/install.sh" || fail "В install.sh Full Restore не переведён на unlimited upload"
  grep -Fq 'data-sg-full-file' "\$root/app/web/templates/maintenance.html" || fail "Нет Full Backup UI V2"
  grep -Fq 'SG_GATEWAY_02110_DOMAIN_EXPORT_FIX1' "\$root/app/clients/exports.py" || fail "Нет domain endpoint policy"
  ! grep -RIl --exclude='*.pyc' --exclude-dir='__pycache__' -E 'CLIENT_TRAFFIC|TRAFFIC3|TRAFFIC2|client_traffic' "\$root/app" "\$root/hostd" >/dev/null || fail "В 021.12 обнаружен код Traffic"
  ! grep -Eq 'nginx -T[^\n]*\|[^\n]*grep[^\n]*-[A-Za-z]*q' "\$root/install.sh" || fail "Остался опасный nginx -T | grep -q"
  ! grep -Eq 'ss -lntp[^\n]*\|[^\n]*grep[^\n]*-[A-Za-z]*q' "\$root/install.sh" || fail "Остался опасный ss | grep -q"
  python3 - "\$root" <<'PYVERIFY'
import ast, json, sys
from pathlib import Path
root=Path(sys.argv[1])

# The source manifest must cover every file that can enter the payload.
# This prevents a valid-but-incomplete manifest from silently dropping
# acceptance assets such as Recovery/Device cleanup CSS.
def ignored(path):
    rel=path.relative_to(root)
    parts=rel.parts
    if rel.as_posix() == 'SOURCE-SHA256SUMS':
        return True
    if any(part in {'.git','.venv','venv','.pytest_cache','.ruff_cache','__pycache__'} for part in parts):
        return True
    if path.suffix in {'.pyc','.pyo'}:
        return True
    name=path.name
    if name.startswith('SG-Gateway-02112-FULL-CLEAN') and (name.endswith('.run') or name.endswith('-TRANSFER.zip') or name.endswith('-SHA256.txt')):
        return True
    return False
actual={p.relative_to(root).as_posix() for p in root.rglob('*') if p.is_file() and not ignored(p)}
listed=set()
for line in (root/'SOURCE-SHA256SUMS').read_text(encoding='utf-8').splitlines():
    if line.strip():
        digest, rel=line.split('  ',1)
        assert len(digest)==64 and rel, line
        listed.add(rel)
missing=sorted(actual-listed)
extra=sorted(listed-actual)
assert not missing, 'SOURCE-SHA256SUMS missing files: ' + ', '.join(missing)
assert not extra, 'SOURCE-SHA256SUMS lists absent files: ' + ', '.join(extra)
for required in ('app/web/static/sg-device-expanded-cleanup-v1.css','app/web/static/sg-recovery-restore-v1.css'):
    assert required in listed, required

for base in (root/'app',root/'hostd',root/'engines'):
    if base.exists():
        for path in base.rglob('*.py'):
            ast.parse(path.read_text(encoding='utf-8'), filename=str(path))
for path in root.rglob('*.json'):
    json.loads(path.read_text(encoding='utf-8'))
exports=(root/'app/clients/exports.py').read_text(encoding='utf-8')
expected='decoded = "' + chr(92) + 'n".join(links)'
rejected='decoded = "' + (chr(92) * 2) + 'n".join(links)'
assert expected in exports, expected
assert rejected not in exports, rejected
PYVERIFY
}

extract_payload
verify_source
case "\${1:-}" in
  --verify-only)
    printf '[SG-Gateway] [OK] %s: binary payload и исходники полностью проверены.\\n' "\$PACKAGE"
    exit 0
    ;;
  --extract-only)
    destination="\${2:-\$PWD/SG-Gateway-02112-SOURCE}"
    rm -rf "\$destination"; mkdir -p "\$destination"
    cp -a "\$TEMP_DIR/\$SOURCE_FOLDER/." "\$destination/"
    printf '[SG-Gateway] [OK] Исходник извлечён: %s\\n' "\$destination"
    exit 0
    ;;
esac
exec bash "\$TEMP_DIR/\$SOURCE_FOLDER/install.sh" "\$@"
exit 1

__SG_GATEWAY_02112_BINARY_PAYLOAD_BELOW__
EOF
cat "$PAYLOAD" >> "$OUT"
chmod +x "$OUT"

# Check the text header separately; the rest of the file is intentionally binary.
awk '/^__SG_GATEWAY_02112_BINARY_PAYLOAD_BELOW__$/ { exit } { print }' "$OUT" | bash -n
"$OUT" --verify-only
RUN_SHA="$(sha256sum "$OUT" | awk '{print $1}')"
printf '%s  %s\n' "$RUN_SHA" "$(basename "$OUT")" > "$SHA_FILE"
rm -f "$TRANSFER_ZIP"
(
  cd "$(dirname "$OUT")"
  zip -q -9 "$(basename "$TRANSFER_ZIP")" "$(basename "$OUT")" "$(basename "$SHA_FILE")"
)

# Verify the exact transfer artifact after extraction.
VERIFY_DIR="$TMP/transfer-check"
mkdir -p "$VERIFY_DIR"
unzip -q "$TRANSFER_ZIP" -d "$VERIFY_DIR"
(
  cd "$VERIFY_DIR"
  sha256sum -c "$(basename "$SHA_FILE")"
  bash "$(basename "$OUT")" --verify-only
)
printf '%s\n' "$OUT"
printf '%s\n' "$TRANSFER_ZIP"
