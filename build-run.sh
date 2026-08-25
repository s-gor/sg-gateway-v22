#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
VERSION="$(tr -d '[:space:]' < "$ROOT/VERSION")"
BUILD_ID="$(tr -d '\r\n' < "$ROOT/BUILD-ID")"
[[ -n "$VERSION" ]] || { echo "[SG-Gateway Build] VERSION is empty" >&2; exit 1; }
[[ -n "$BUILD_ID" ]] || { echo "[SG-Gateway Build] BUILD-ID is empty" >&2; exit 1; }

DEFAULT_BASENAME="SG-Gateway-${VERSION}-FULL"
OUT="${1:-$ROOT/${DEFAULT_BASENAME}.run}"
SOURCE_FOLDER="SG-Gateway-${VERSION}-SOURCE"
PAYLOAD_MARKER="__SG_GATEWAY_BINARY_PAYLOAD_V1__"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
STAGE="$TMP/$SOURCE_FOLDER"
PAYLOAD="$TMP/payload.tar.gz"
SHA_FILE="${OUT%.run}-SHA256.txt"
TRANSFER_ZIP="${OUT%.run}-TRANSFER.zip"

mkdir -p "$STAGE"
if command -v git >/dev/null 2>&1 && git -C "$ROOT" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  SOURCE_SHA="$(git -C "$ROOT" rev-parse HEAD)"
  SOURCE_TREE="$(git -C "$ROOT" rev-parse HEAD^{tree})"
  git -C "$ROOT" archive --format=tar HEAD | tar -C "$STAGE" -xf -
  SOURCE_DATE_EPOCH="${SOURCE_DATE_EPOCH:-$(git -C "$ROOT" show -s --format=%ct HEAD)}"
else
  SOURCE_SHA="${SG_GATEWAY_SOURCE_SHA:-}"
  SOURCE_TREE="${SG_GATEWAY_SOURCE_TREE:-}"
  [[ "$SOURCE_SHA" =~ ^[0-9a-f]{40}$ ]] || { echo "[SG-Gateway Build] SG_GATEWAY_SOURCE_SHA must be an exact commit SHA" >&2; exit 1; }
  [[ "$SOURCE_TREE" =~ ^[0-9a-f]{40}$ ]] || { echo "[SG-Gateway Build] SG_GATEWAY_SOURCE_TREE must be an exact Git tree SHA" >&2; exit 1; }
  tar -C "$ROOT" \
    --exclude='./.git' \
    --exclude='./.venv' \
    --exclude='./venv' \
    --exclude='./.pytest_cache' \
    --exclude='./.ruff_cache' \
    --exclude='*/__pycache__' \
    --exclude='*.pyc' \
    --exclude='*.pyo' \
    --exclude='./SG-Gateway-*-FULL*.run' \
    --exclude='./SG-Gateway-*-FULL*-TRANSFER.zip' \
    --exclude='./SG-Gateway-*-FULL*-SHA256.txt' \
    -cf - . | tar -C "$STAGE" -xf -
  SOURCE_DATE_EPOCH="${SOURCE_DATE_EPOCH:-0}"
fi
[[ "$SOURCE_SHA" =~ ^[0-9a-f]{40}$ ]] || { echo "[SG-Gateway Build] source SHA is invalid" >&2; exit 1; }
[[ "$SOURCE_TREE" =~ ^[0-9a-f]{40}$ ]] || { echo "[SG-Gateway Build] source tree is invalid" >&2; exit 1; }
[[ "$SOURCE_DATE_EPOCH" =~ ^[0-9]+$ ]] || SOURCE_DATE_EPOCH=0

[[ "$(tr -d '[:space:]' < "$STAGE/VERSION")" == "$VERSION" ]] || { echo "[SG-Gateway Build] VERSION mismatch" >&2; exit 1; }
[[ "$(tr -d '\r\n' < "$STAGE/BUILD-ID")" == "$BUILD_ID" ]] || { echo "[SG-Gateway Build] BUILD-ID mismatch" >&2; exit 1; }
(cd "$STAGE" && sha256sum -c SOURCE-SHA256SUMS >/dev/null)
if [[ -f "$STAGE/vendor/cores/SHA256SUMS" ]]; then
  (cd "$STAGE/vendor/cores" && sha256sum -c SHA256SUMS >/dev/null)
fi
python3 - "$STAGE/PACKAGE-SOURCE.json" "$SOURCE_SHA" "$SOURCE_TREE" <<'PYSOURCE'
import json
import sys
from pathlib import Path

Path(sys.argv[1]).write_text(
    json.dumps(
        {"source_sha": sys.argv[2], "source_tree": sys.argv[3]},
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    ) + "\n",
    encoding="utf-8",
)
PYSOURCE

tar --sort=name --mtime="@${SOURCE_DATE_EPOCH}" --owner=0 --group=0 --numeric-owner \
  -C "$TMP" -czf "$PAYLOAD" "$SOURCE_FOLDER"
PAYLOAD_SHA="$(sha256sum "$PAYLOAD" | awk '{print $1}')"
PACKAGE="SG-Gateway ${VERSION} (${BUILD_ID})"

{
  printf '%s\n' '#!/usr/bin/env bash' 'set -Eeuo pipefail'
  printf 'PACKAGE=%q\n' "$PACKAGE"
  printf 'EXPECTED_VERSION=%q\n' "$VERSION"
  printf 'EXPECTED_BUILD_ID=%q\n' "$BUILD_ID"
  printf 'EXPECTED_SOURCE_SHA=%q\n' "$SOURCE_SHA"
  printf 'EXPECTED_SOURCE_TREE=%q\n' "$SOURCE_TREE"
  printf 'SOURCE_FOLDER=%q\n' "$SOURCE_FOLDER"
  printf 'PAYLOAD_SHA256=%q\n' "$PAYLOAD_SHA"
  printf 'PAYLOAD_MARKER=%q\n' "$PAYLOAD_MARKER"
} > "$OUT"

cat >> "$OUT" <<'EOSG'
SELF="$(readlink -f "${BASH_SOURCE[0]}")"
TEMP_DIR=""

cleanup() { [[ -z "${TEMP_DIR:-}" || ! -d "$TEMP_DIR" ]] || rm -rf "$TEMP_DIR"; }
trap cleanup EXIT INT TERM
fail() { printf '[SG-Gateway] [ERROR] %s\n' "$*" >&2; exit 1; }

extract_payload() {
  local command payload actual payload_line token
  for command in awk tail sha256sum tar python3 bash readlink mktemp; do
    command -v "$command" >/dev/null 2>&1 || fail "Не найдена команда: $command"
  done
  token="${EXPECTED_VERSION//[^A-Za-z0-9]/}"
  TEMP_DIR="$(mktemp -d "/tmp/sg-gateway-${token}.XXXXXX")"
  payload="$TEMP_DIR/payload.tar.gz"
  payload_line="$(awk -v marker="$PAYLOAD_MARKER" '$0 == marker { print NR + 1; exit }' "$SELF")"
  [[ "$payload_line" =~ ^[0-9]+$ ]] || fail "Не найден встроенный binary payload"
  tail -n "+$payload_line" "$SELF" > "$payload" || fail "Не удалось извлечь встроенный payload"
  actual="$(sha256sum "$payload" | awk '{print $1}')"
  [[ "$actual" == "$PAYLOAD_SHA256" ]] || fail "Контрольная сумма payload не совпала"
  tar -xzf "$payload" -C "$TEMP_DIR" || fail "Не удалось распаковать payload"
  [[ -d "$TEMP_DIR/$SOURCE_FOLDER" ]] || fail "Каталог исходника не извлечён"
}

verify_source() {
  local root shell_file
  root="$TEMP_DIR/$SOURCE_FOLDER"
  [[ "$(tr -d '[:space:]' < "$root/VERSION")" == "$EXPECTED_VERSION" ]] || fail "Версия payload не совпала"
  [[ "$(tr -d '\r\n' < "$root/BUILD-ID")" == "$EXPECTED_BUILD_ID" ]] || fail "Build ID payload не совпал"
  python3 "$root/scripts/package_contract.py" "$root" "$EXPECTED_SOURCE_SHA" >/dev/null || fail "Package manifest, payload, source SHA или AWG31 runtime assets не прошли проверку"
  (cd "$root" && sha256sum -c SOURCE-SHA256SUMS >/dev/null) || fail "Файлы исходника повреждены"
  if [[ -f "$root/vendor/cores/SHA256SUMS" ]]; then
    (cd "$root/vendor/cores" && sha256sum -c SHA256SUMS >/dev/null) || fail "Vendored engines повреждены"
  fi
  find "$root" -type f -name '*.sh' -exec bash -n {} \; || \
    fail "Ошибка shell-синтаксиса в package payload"

  [[ "$(sha256sum "$root/assets/placeholder/index.html" | awk '{print $1}')" == "06b280bab43d9ed4ceeb75d34008b60158366a968e6eb950b3e0b4b0cbcdd226" ]] || fail "Заглушка не совпала с принятой"
  grep -Fq 'SG_GATEWAY_02110_HTTPS_VERIFY_RETRY_FIX1' "$root/deploy/configure-panel-access.sh" || fail "Нет HTTPS retry"
  grep -Fq '/root/sg-gateway-02112-installer-resume.env' "$root/deploy/full-uninstall-ubuntu.sh" || fail "Uninstall не очищает current resume 02112"
  grep -Fq '/root/sg-gateway-02111-installer-resume.env' "$root/deploy/full-uninstall-ubuntu.sh" || fail "Uninstall не очищает resume 02111"
  grep -Fq 'PYNGINXCLEAN' "$root/deploy/full-uninstall-ubuntu.sh" || fail "Uninstall не содержит current nginx cleanup block"
  grep -Fq 'sg-gateway-443' "$root/deploy/full-uninstall-ubuntu.sh" || fail "Uninstall не содержит exact SG stream filename cleanup"
  grep -Fq 'stream-conf' "$root/deploy/full-uninstall-ubuntu.sh" || fail "Uninstall не содержит SG stream include cleanup"
  grep -Fq '*.conf' "$root/deploy/full-uninstall-ubuntu.sh" || fail "Uninstall не содержит historical wildcard stream compatibility"
  grep -Fq 'SG_DEVICE_COLLAPSE_V4_LAST_CSS' "$root/app/web/templates/base.html" || fail "Нет финального Device Collapse V4"
  grep -Fq 'SG_DEVICE_EXPANDED_CLEANUP_V1_LAST_CSS' "$root/app/web/templates/base.html" || fail "Нет очистки раскрытой карточки устройства"
  grep -Fq 'def recovery_restore_backup_route(name: str):' "$root/app/main.py" || fail "Нет восстановления из Recovery"
  grep -Fq 'data-recovery-restore' "$root/app/web/templates/recovery.html" || fail "Нет кнопки восстановления в Recovery"
  grep -Fq 'System alignment final fix 3 — Disk is the reference' "$root/app/web/static/sg-system-simple-dials-v1.css" || fail "Нет финального System FIX3"
  grep -Fq 'Скопировать ссылку' "$root/app/web/templates/client_detail.html" || fail "Нет принятой кнопки подписки"
  grep -Fq 'SG_GATEWAY_02110_INSTALLER_SAFETY_FIX2' "$root/install.sh" || fail "Нет installer safety fix 2"
  grep -Fq 'SG_GATEWAY_02110_SYSTEMD_TRANSIENT_RETRY_FIX3' "$root/install.sh" || fail "Нет systemd transient retry fix 3"
  grep -Fq 'SG_GATEWAY_02110_UNINSTALL_SAFETY_FIX2' "$root/deploy/full-uninstall-ubuntu.sh" || fail "Нет uninstall safety fix 2"
  grep -Fq 'def restore_uploaded_full_backup' "$root/hostd/sg_hostd/full_backup_runtime.py" || fail "Нет Full Backup runtime"
  grep -Fq 'backup.full.restore.start' "$root/hostd/sg_hostd/commands.py" || fail "Нет фонового Full Restore"
  grep -Fq 'FULL_BACKUP_PANEL_DATA_PERMISSIONS_FIX3' "$root/hostd/sg_hostd/full_backup_runtime.py" || fail "Нет исправления прав SQLite"
  grep -Fq 'SG_GATEWAY_02111_PORTABLE_RESTORE_V2' "$root/hostd/sg_hostd/full_backup_runtime.py" || fail "Нет portable restore V2"
  grep -Fq 'SG_GATEWAY_02111_PORTABLE_HOST_REBIND' "$root/hostd/sg_hostd/full_backup_runtime.py" || fail "Restore не привязывает state к новому IP"
  grep -Fq 'SG_GATEWAY_02111_REGENERATE_RUNTIME_FROM_STATE' "$root/hostd/sg_hostd/full_backup_runtime.py" || fail "Restore не пересобирает runtime"
  grep -Fq 'portable_runtime_regenerated' "$root/hostd/sg_hostd/full_backup_runtime.py" || fail "Restore не подтверждает пересборку runtime"
  grep -Fq 'SG_GATEWAY_02111_OPERATION_JOB_PRESERVE_FIX' "$root/hostd/sg_hostd/full_backup_runtime.py" || fail "Restore может затереть live job log при rollback"
  grep -Fq 'SG_GATEWAY_02111_RESTORE_SESSION_PRESERVE_FIX' "$root/hostd/sg_hostd/full_backup_runtime.py" || fail "Restore не сохраняет session secret нового сервера"
  grep -Fq '"SG_GATEWAY_SECRET_KEY"' "$root/hostd/sg_hostd/full_backup_runtime.py" || fail "SG_GATEWAY_SECRET_KEY не сохранён при portable restore"
  grep -Fq 'SG_GATEWAY_02111_RESTORE_HTTPS_BOOTSTRAP_FIX' "$root/deploy/configure-panel-access.sh" || fail "Нет bootstrap HTTPS из локальных сертификатов"
  grep -Fq 'id="opjob-refresh"' "$root/app/web/templates/operation_job.html" || fail "Нет кнопки обновления страницы Full Restore"
  grep -Fq 'SG_GATEWAY_02111_RESTORE_RESTART_PAGE_FIX' "$root/deploy/configure-panel-access.sh" || fail "HTTPS vhost не показывает restart page при backend restart"
  grep -Fq 'SG_GATEWAY_02111_RESTORE_RESTART_PAGE_FIX' "$root/install.sh" || fail "Initial panel vhost не показывает restart page"
  [[ -f "$root/assets/placeholder/restarting.html" ]] || fail "Нет статической restart page"
  grep -Fq 'SG_GATEWAY_FULL_BACKUP_UPLOAD_FIX1' "$root/deploy/configure-panel-access.sh" || fail "Нет upload limit для Full Restore"
  grep -Fq 'SG_GATEWAY_02111_CUMULATIVE_FULL_RESTORE_UPLOAD_FIX' "$root/install.sh" || fail "Clean/update installer не гарантирует upload limit Full Restore"
  grep -Fq 'client_max_body_size 0;' "$root/install.sh" || fail "В install.sh Full Restore не переведён на unlimited upload"
  grep -Fq 'data-sg-full-file' "$root/app/web/templates/maintenance.html" || fail "Нет Full Backup UI V2"
  grep -Fq 'SG_GATEWAY_02110_DOMAIN_EXPORT_FIX1' "$root/app/clients/exports.py" || fail "Нет domain endpoint policy"
  ! grep -RIl --exclude='*.pyc' --exclude-dir='__pycache__' -E 'CLIENT_TRAFFIC|TRAFFIC3|TRAFFIC2|client_traffic' "$root/app" "$root/hostd" >/dev/null || fail "В 021.12 обнаружен код Traffic"
  ! grep -Eq 'nginx -T[^\n]*\|[^\n]*grep[^\n]*-[A-Za-z]*q' "$root/install.sh" || fail "Остался опасный nginx -T | grep -q"
  ! grep -Eq 'ss -lntp[^\n]*\|[^\n]*grep[^\n]*-[A-Za-z]*q' "$root/install.sh" || fail "Остался опасный ss | grep -q"
  python3 - "$root" "$EXPECTED_VERSION" "$EXPECTED_BUILD_ID" <<'PYVERIFY'
import ast
import json
import re
import sys
from pathlib import Path

root = Path(sys.argv[1])
expected_version = sys.argv[2]
expected_build = sys.argv[3]

listed = set()
for line_no, raw in enumerate((root / "SOURCE-SHA256SUMS").read_text(encoding="utf-8").splitlines(), 1):
    if not raw.strip():
        continue
    match = re.fullmatch(r"([0-9a-f]{64})  (.+)", raw)
    if match is None:
        raise SystemExit(f"invalid SOURCE-SHA256SUMS line {line_no}: {raw!r}")
    listed.add(match.group(2))
actual = {
    path.relative_to(root).as_posix()
    for path in root.rglob("*")
    if path.is_file() and path.relative_to(root).as_posix() not in {"SOURCE-SHA256SUMS", "PACKAGE-SOURCE.json"}
}
missing = sorted(actual - listed)
extra = sorted(listed - actual)
if missing:
    raise SystemExit("SOURCE-SHA256SUMS missing files: " + ", ".join(missing[:20]))
if extra:
    raise SystemExit("SOURCE-SHA256SUMS lists absent files: " + ", ".join(extra[:20]))
for required in (
    "app/web/static/sg-device-expanded-cleanup-v1.css",
    "app/web/static/sg-recovery-restore-v1.css",
):
    if required not in listed:
        raise SystemExit(f"required acceptance asset missing from SOURCE-SHA256SUMS: {required}")

for base_name in ("app", "hostd", "engines", "deploy", "tests"):
    base = root / base_name
    if base.exists():
        for path in base.rglob("*.py"):
            ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
for path in root.rglob("*.json"):
    json.loads(path.read_text(encoding="utf-8"))

manifest = json.loads((root / "release-manifest.json").read_text(encoding="utf-8"))
if manifest.get("version") != expected_version:
    raise SystemExit("release-manifest VERSION mismatch")
if (root / "BUILD-ID").read_text(encoding="utf-8").strip() != expected_build:
    raise SystemExit("BUILD-ID mismatch")
for required in ("install.sh", "deploy/update-from-github.sh", "deploy/install-from-github.sh"):
    if not (root / required).is_file():
        raise SystemExit(f"missing required source file: {required}")
PYVERIFY
}

extract_payload
verify_source
case "${1:-}" in
  --verify-only)
    printf '[SG-Gateway] [OK] %s: binary payload и исходники полностью проверены. Source SHA: %s; tree: %s.\n' "$PACKAGE" "$EXPECTED_SOURCE_SHA" "$EXPECTED_SOURCE_TREE"
    exit 0
    ;;
  --extract-only)
    destination="${2:-$PWD/$SOURCE_FOLDER}"
    rm -rf "$destination"
    mkdir -p "$destination"
    cp -a "$TEMP_DIR/$SOURCE_FOLDER/." "$destination/"
    printf '[SG-Gateway] [OK] Исходник извлечён: %s\n' "$destination"
    exit 0
    ;;
esac
exec bash "$TEMP_DIR/$SOURCE_FOLDER/install.sh" "$@"
EOSG

printf '\n%s\n' "$PAYLOAD_MARKER" >> "$OUT"
cat "$PAYLOAD" >> "$OUT"
chmod +x "$OUT"

awk -v marker="$PAYLOAD_MARKER" '$0 == marker { exit } { print }' "$OUT" | bash -n
"$OUT" --verify-only
RUN_SHA="$(sha256sum "$OUT" | awk '{print $1}')"
printf '%s  %s\n' "$RUN_SHA" "$(basename "$OUT")" > "$SHA_FILE"
rm -f "$TRANSFER_ZIP"
(
  cd "$(dirname "$OUT")"
  zip -q -9 "$(basename "$TRANSFER_ZIP")" "$(basename "$OUT")" "$(basename "$SHA_FILE")"
)

# Verify the exact transfer artifact after extraction, not only the pre-ZIP files.
VERIFY_DIR="$TMP/transfer-check"
mkdir -p "$VERIFY_DIR"
unzip -q "$TRANSFER_ZIP" -d "$VERIFY_DIR"
(
  cd "$VERIFY_DIR"
  sha256sum -c "$(basename "$SHA_FILE")"
  bash "$(basename "$OUT")" --verify-only
)
printf '[SG-Gateway Build] RUN: %s\n' "$OUT"
printf '[SG-Gateway Build] SHA256: %s\n' "$SHA_FILE"
printf '[SG-Gateway Build] TRANSFER: %s\n' "$TRANSFER_ZIP"
