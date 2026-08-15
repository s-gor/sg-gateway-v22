#!/usr/bin/env bash
set -Eeuo pipefail
MODE=""; HOST=""; PUBLIC_PORT=""
APP_ROOT="/opt/sg-gateway"
ENV_FILE="/etc/sg-gateway/sg-gateway.env"
RUNTIME_ENV="/etc/sg-gateway/runtime.env"
STATE_DIR="/var/lib/sg-gateway/security"
STATE_FILE="$STATE_DIR/tls-state.json"
BACKUP_ROOT="$STATE_DIR/backups"
NGINX_MAIN="/etc/nginx/nginx.conf"
NGINX_CONF="/etc/nginx/sites-available/sg-gateway"
NGINX_LINK="/etc/nginx/sites-enabled/sg-gateway"
ACME_CONF="/etc/nginx/sites-available/sg-gateway-acme"
ACME_LINK="/etc/nginx/sites-enabled/sg-gateway-acme"
STREAM_CONF="/etc/nginx/stream-conf.d/sg-gateway-443.conf"
ACME_ROOT="/var/www/sg-gateway-acme"
PLACEHOLDER_ROOT="/var/www/sg-gateway-placeholder"
PLACEHOLDER_SOURCE="$APP_ROOT/assets/placeholder/index.html"
RESTART_SOURCE="$APP_ROOT/assets/placeholder/restarting.html"
RENEW_HOOK="/etc/letsencrypt/renewal-hooks/deploy/reload-sg-gateway-nginx.sh"
PANEL_USER="sg-gateway"; PANEL_GROUP="sg-gateway"
XRAY_INTERNAL_PORT="7443"; PLACEHOLDER_TLS_INTERNAL_PORT="7444"
SG_HTTPS_BACKUP_DIR=""
SG_HTTPS_COMMITTED=0
log(){ printf '[SG-Gateway HTTPS] %s\n' "$*"; }
fail(){ printf '[SG-Gateway HTTPS] ОШИБКА: %s\n' "$*" >&2; exit 1; }
usage(){ printf '%s\n' 'configure-panel-access.sh --mode https --host panel.example.com --port 63443' 'configure-panel-access.sh --mode renew|rollback|refresh'; }
while [[ $# -gt 0 ]]; do case "$1" in --mode) MODE="${2:-}"; shift 2;; --host) HOST="${2:-}"; shift 2;; --port) PUBLIC_PORT="${2:-}"; shift 2;; -h|--help) usage; exit 0;; *) fail "неизвестный параметр: $1";; esac; done
[[ $EUID -eq 0 ]] || fail "запустите скрипт от root"
[[ "$MODE" =~ ^(https|renew|rollback|refresh)$ ]] || { usage; exit 1; }
[[ -f "$ENV_FILE" && -f "$RUNTIME_ENV" ]] || fail "не найдены файлы установленного SG-Gateway"
get_env(){ local file="$1" key="$2" default="$3" value; value="$(grep -E "^${key}=" "$file" 2>/dev/null | tail -1 | cut -d= -f2- || true)"; printf '%s' "${value:-$default}"; }
BACKEND_PORT="$(get_env "$ENV_FILE" SG_GATEWAY_PORT 18080)"
CONFIGURED_PUBLIC_PORT="$(get_env "$ENV_FILE" SG_GATEWAY_PUBLIC_PORT 63443)"
# SG_GATEWAY_02111_SECURITY_STATE_PATH_RESTORE_FIX
STATE_DIR="$(get_env "$ENV_FILE" SG_GATEWAY_SECURITY_STATE_DIR /var/lib/sg-gateway/security)"
STATE_FILE="$STATE_DIR/tls-state.json"
BACKUP_ROOT="$STATE_DIR/backups"
PUBLIC_PORT="${PUBLIC_PORT:-$CONFIGURED_PUBLIC_PORT}"
REALITY_SNI="$(get_env "$RUNTIME_ENV" SG_GATEWAY_REALITY_SNI www.bing.com)"; REALITY_SNI="${REALITY_SNI,,}"
[[ "$BACKEND_PORT" =~ ^[0-9]+$ && "$PUBLIC_PORT" =~ ^[0-9]+$ ]] || fail "некорректный порт"
[[ "$PUBLIC_PORT" == "$CONFIGURED_PUBLIC_PORT" ]] || fail "порт должен совпадать с установленным портом панели $CONFIGURED_PUBLIC_PORT"
case "$PUBLIC_PORT" in 22|80|443|585|7443|7444|8090|18080) fail "порт $PUBLIC_PORT зарезервирован";; esac
for command in nginx certbot openssl getent curl python3 systemctl cmp; do command -v "$command" >/dev/null 2>&1 || fail "не найден $command"; done
install -d -m 0750 -o "$PANEL_USER" -g "$PANEL_GROUP" "$STATE_DIR"
install -d -m 0750 -o root -g "$PANEL_GROUP" "$BACKUP_ROOT"
install -d -m 0755 "$ACME_ROOT/.well-known/acme-challenge" "$PLACEHOLDER_ROOT" /etc/nginx/sites-available /etc/nginx/sites-enabled /etc/nginx/stream-conf.d /etc/letsencrypt/renewal-hooks/deploy
install -m 0644 "$PLACEHOLDER_SOURCE" "$PLACEHOLDER_ROOT/index.html"
install -m 0644 "$RESTART_SOURCE" "$PLACEHOLDER_ROOT/restarting.html"
read_state_value(){ python3 - "$STATE_FILE" "$1" <<'PY'
import json,sys
from pathlib import Path
try: data=json.loads(Path(sys.argv[1]).read_text(encoding='utf-8'))
except Exception: data={}
print(data.get(sys.argv[2], '') or '')
PY
}
write_state(){ local domain="$1" action="$2" message="$3" backup_name="${4:-}"; python3 - "$STATE_FILE" "$domain" "$PUBLIC_PORT" "$BACKEND_PORT" "$action" "$message" "$backup_name" "$PANEL_GROUP" <<'PY'
import grp,json,os,subprocess,sys
from datetime import datetime,timezone
from pathlib import Path
path=Path(sys.argv[1]); domain=sys.argv[2]; public_port=int(sys.argv[3]); backend_port=int(sys.argv[4]); action=sys.argv[5]; message=sys.argv[6]; backup=sys.argv[7]; group=sys.argv[8]
cert=Path(f'/etc/letsencrypt/live/{domain}/fullchain.pem'); key=Path(f'/etc/letsencrypt/live/{domain}/privkey.pem'); certificate={}
try:
 r=subprocess.run(['openssl','x509','-in',str(cert),'-noout','-subject','-issuer','-startdate','-enddate','-serial'],capture_output=True,text=True,timeout=15,check=False)
 if r.returncode==0:
  p={}
  for line in r.stdout.splitlines():
   if '=' in line: k,v=line.split('=',1); p[k.strip().lower()]=v.strip()
  certificate={'subject':p.get('subject',''),'issuer':p.get('issuer',''),'not_before':p.get('notbefore',''),'not_after':p.get('notafter',''),'serial':p.get('serial','')}
except Exception: pass
payload={'domain':domain,'public_port':public_port,'panel_port':public_port,'backend_port':backend_port,'https_ready':bool(certificate),'certificate':certificate,'certificate_path':str(cert),'key_path':str(key),'last_action':action,'last_message':message,'updated_at':datetime.now(timezone.utc).isoformat(),'backup':backup}
path.parent.mkdir(parents=True,exist_ok=True); tmp=path.with_name(path.name+'.new'); tmp.write_text(json.dumps(payload,ensure_ascii=False,indent=2,sort_keys=True)+'\n',encoding='utf-8'); os.chmod(tmp,0o640)
try: os.chown(tmp,0,grp.getgrnam(group).gr_gid)
except KeyError: pass
os.replace(tmp,path)
PY
}
backup_path(){ local src="$1" name="$2" dir="$3"; [[ -e "$src" || -L "$src" ]] && cp -a "$src" "$dir/$name" || true; }
restore_path(){ local src="$1" dst="$2"; rm -rf "$dst"; if [[ -e "$src" || -L "$src" ]]; then mkdir -p "$(dirname "$dst")"; cp -a "$src" "$dst"; fi; }
create_backup(){ local dir="$BACKUP_ROOT/$(date -u +%Y%m%d-%H%M%S)-panel-access"; install -d -m 0750 -o root -g "$PANEL_GROUP" "$dir"; backup_path "$NGINX_MAIN" nginx.conf "$dir"; backup_path "$NGINX_CONF" nginx-site "$dir"; backup_path "$NGINX_LINK" nginx-link "$dir"; backup_path "$ACME_CONF" acme-site "$dir"; backup_path "$ACME_LINK" acme-link "$dir"; backup_path "$STREAM_CONF" stream-conf "$dir"; backup_path "$STATE_FILE" tls-state.json "$dir"; backup_path "$RENEW_HOOK" renewal-hook "$dir"; printf '%s' "$dir"; }
restore_backup(){ local dir="$1"; restore_path "$dir/nginx.conf" "$NGINX_MAIN"; restore_path "$dir/nginx-site" "$NGINX_CONF"; restore_path "$dir/nginx-link" "$NGINX_LINK"; restore_path "$dir/acme-site" "$ACME_CONF"; restore_path "$dir/acme-link" "$ACME_LINK"; restore_path "$dir/stream-conf" "$STREAM_CONF"; restore_path "$dir/tls-state.json" "$STATE_FILE"; restore_path "$dir/renewal-hook" "$RENEW_HOOK"; }
ensure_stream_include(){ python3 - "$NGINX_MAIN" <<'PY'
from pathlib import Path
import re
import sys
p=Path(sys.argv[1]); b=p.read_text(encoding='utf-8')
direct='    include /etc/nginx/stream-conf.d/sg-gateway-443.conf;'
pattern=re.compile(r'(?m)^\s*include\s+/etc/nginx/stream-conf\.d/(?:\*\.conf|sg-gateway-443\.conf);\s*$')
existing=pattern.findall(b)
if len(existing)>1:
 kept=False; lines=[]
 for line in b.splitlines():
  if pattern.fullmatch(line):
   if kept: continue
   line=direct; kept=True
  lines.append(line)
 b='\n'.join(lines)+('\n' if b.endswith('\n') else '')
elif not existing:
 if 'stream {' in b:
  pos=b.index('stream {')+len('stream {'); b=b[:pos]+'\n'+direct+b[pos:]
 else: b=b.rstrip()+'\n\n# SG_GATEWAY_PLACEHOLDER_80_443_V3\nstream {\n'+direct+'\n}\n'
p.write_text(b,encoding='utf-8',newline='\n')
PY
}
nginx_cookie_security_directive(){ local version="$(nginx -v 2>&1 | sed -n 's#^nginx version: nginx/\([^ ]*\).*$#\1#p')"; if [[ -n "$version" ]] && command -v dpkg >/dev/null 2>&1 && dpkg --compare-versions "$version" ge '1.19.3'; then printf '%s' 'proxy_cookie_flags ~ secure httponly samesite=lax;'; else printf '%s' 'proxy_cookie_path / "/; Secure; HttpOnly; SameSite=Lax";'; fi; }
write_stream_config(){ local default_backend="$1"; cat > "$STREAM_CONF" <<EOF
# SG_GATEWAY_PLACEHOLDER_80_443_V3
map \$ssl_preread_server_name \$sg_gateway_443_backend {
    hostnames;
    $REALITY_SNI 127.0.0.1:$XRAY_INTERNAL_PORT;
    default $default_backend;
}
server {
    listen 443;
    listen [::]:443;
    proxy_pass \$sg_gateway_443_backend;
    ssl_preread on;
    proxy_connect_timeout 10s;
    proxy_timeout 1h;
}
EOF
}
write_https_site(){ local domain="$1" cert="$2" key="$3" cookie_security_directive="$(nginx_cookie_security_directive)"; cat > "$NGINX_CONF" <<EOF
# SG_GATEWAY_PLACEHOLDER_80_443_V3
server {
    listen 80 default_server;
    listen [::]:80 default_server;
    server_name $domain _;
    root $PLACEHOLDER_ROOT;
    index index.html;
    location ^~ /.well-known/acme-challenge/ { root $ACME_ROOT; default_type text/plain; }
    location = / { try_files /index.html =404; add_header Cache-Control "no-cache" always; add_header X-Content-Type-Options "nosniff" always; add_header X-Frame-Options "SAMEORIGIN" always; add_header Referrer-Policy "strict-origin-when-cross-origin" always; }
    location = /index.html { try_files /index.html =404; add_header Cache-Control "no-cache" always; add_header X-Content-Type-Options "nosniff" always; add_header X-Frame-Options "SAMEORIGIN" always; add_header Referrer-Policy "strict-origin-when-cross-origin" always; }
    location / { return 404; }
}
server {
    listen 127.0.0.1:$PLACEHOLDER_TLS_INTERNAL_PORT ssl;
    server_name $domain;
    ssl_certificate $cert;
    ssl_certificate_key $key;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_session_cache shared:SG_GATEWAY_PLACEHOLDER_TLS:5m;
    ssl_session_timeout 1d;
    ssl_session_tickets off;
    root $PLACEHOLDER_ROOT;
    index index.html;
    location = / { try_files /index.html =404; add_header Cache-Control "no-cache" always; add_header X-Content-Type-Options "nosniff" always; add_header X-Frame-Options "SAMEORIGIN" always; add_header Referrer-Policy "strict-origin-when-cross-origin" always; }
    location = /index.html { try_files /index.html =404; add_header Cache-Control "no-cache" always; add_header X-Content-Type-Options "nosniff" always; add_header X-Frame-Options "SAMEORIGIN" always; add_header Referrer-Policy "strict-origin-when-cross-origin" always; }
    location / { return 404; }
}
server {
    listen $PUBLIC_PORT ssl;
    listen [::]:$PUBLIC_PORT ssl;
    server_name $domain;
    error_page 497 =308 https://$domain:$PUBLIC_PORT\$request_uri;
    ssl_certificate $cert;
    ssl_certificate_key $key;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_session_cache shared:SG_GATEWAY_TLS:10m;
    ssl_session_timeout 1d;
    ssl_session_tickets off;
    add_header Strict-Transport-Security "max-age=31536000" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header Referrer-Policy "strict-origin-when-cross-origin" always;
    # SG_GATEWAY_02111_RESTORE_RESTART_PAGE_FIX
    error_page 502 503 504 =200 /__sg_gateway_restarting;
    location = /__sg_gateway_restarting {
        internal;
        root $PLACEHOLDER_ROOT;
        try_files /restarting.html =502;
        default_type text/html;
        add_header Cache-Control "no-store" always;
    }
    # SG_GATEWAY_FULL_BACKUP_UPLOAD_FIX1
    location = /maintenance/full-backups/restore {
        client_max_body_size 1024m;
        proxy_pass http://127.0.0.1:$BACKEND_PORT;
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto https;
        proxy_read_timeout 300s;
        proxy_send_timeout 300s;
    }
    location / {
        proxy_pass http://127.0.0.1:$BACKEND_PORT;
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto https;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection "upgrade";
        $cookie_security_directive
        proxy_read_timeout 120s;
    }
}
EOF
rm -f "$ACME_LINK" "$ACME_CONF" /etc/nginx/sites-enabled/default; ln -sfn "$NGINX_CONF" "$NGINX_LINK"; }
wait_backend(){ local i; for i in $(seq 1 45); do curl -fsS --max-time 3 "http://127.0.0.1:$BACKEND_PORT/health" >/dev/null 2>&1 && return 0; sleep 1; done; fail "backend панели не отвечает"; }
# SG_GATEWAY_02110_HTTPS_VERIFY_RETRY_FIX1
wait_placeholder_contract(){
  local scheme="$1" port="$2" domain="$3" label="$4"
  local output code attempt
  output="$(mktemp)"
  for attempt in $(seq 1 30); do
    code="$(curl --noproxy '*' -ksS --max-time 5 \
      --resolve "$domain:$port:127.0.0.1" \
      -o "$output" -w '%{http_code}' \
      "$scheme://$domain/" 2>/dev/null || true)"
    if [[ "$code" == "200" ]] && cmp -s "$output" "$PLACEHOLDER_ROOT/index.html"; then
      rm -f "$output"
      log "$label: OK"
      return 0
    fi
    sleep 1
  done
  rm -f "$output"
  fail "$label не прошёл проверку после перезагрузки Nginx (HTTP ${code:-000})"
}

wait_panel_contract(){
  local domain="$1" code="" attempt
  for attempt in $(seq 1 30); do
    code="$(curl --noproxy '*' -ksS --max-time 5 \
      --resolve "$domain:$PUBLIC_PORT:127.0.0.1" \
      -o /dev/null -w '%{http_code}' \
      "https://$domain:$PUBLIC_PORT/health" 2>/dev/null || true)"
    [[ "$code" == "200" ]] && { log "Панель HTTPS $PUBLIC_PORT: OK"; return 0; }
    sleep 1
  done
  fail "панель не отвечает на $PUBLIC_PORT после перезагрузки Nginx (HTTP ${code:-000})"
}

verify_https_contract(){
  local domain="$1"
  # systemctl reload returns before every old worker has exited. During that
  # short interval the temporary ACME vhost can still answer HTTP 404.
  wait_placeholder_contract http 80 "$domain" "HTTP 80"
  wait_placeholder_contract https 443 "$domain" "HTTPS 443 fallback"
  wait_panel_contract "$domain"
  grep -Fq "$REALITY_SNI 127.0.0.1:$XRAY_INTERNAL_PORT;" "$STREAM_CONF" || fail "SNI Reality не направлен в Xray"
  grep -Fq "default 127.0.0.1:$PLACEHOLDER_TLS_INTERNAL_PORT;" "$STREAM_CONF" || fail "browser fallback не направлен на заглушку"
  systemctl is-active --quiet nginx.service || fail "Nginx не активен"
  # SG_GATEWAY_02111_RESTORE_HTTPS_BOOTSTRAP_FIX
  if [[ "${SG_GATEWAY_HTTPS_DEFER_XRAY_CHECK:-0}" == "1" ]]; then
    log "Xray: проверка активности отложена до пересборки runtime"
  else
    systemctl is-active --quiet xray.service || fail "Xray не активен"
  fi
}
# SG_GATEWAY_02111_XRAY_FULL_ACCESS_POLICY
xray_full_access(){ [[ ! -d /usr/local/etc/xray ]] || chmod -R 0777 /usr/local/etc/xray; }
apply_client_runtime(){ local output; if output="$(cd "$APP_ROOT" && PYTHONPATH="$APP_ROOT:$APP_ROOT/hostd" "$APP_ROOT/.venv/bin/python" - "$ENV_FILE" "$RUNTIME_ENV" /etc/sg-gateway/engine-secrets.env <<'PY'
import json,os,shlex,sys
from pathlib import Path
for filename in sys.argv[1:]:
 p=Path(filename)
 if not p.is_file(): continue
 for raw in p.read_text(encoding='utf-8').splitlines():
  line=raw.strip()
  if not line or line.startswith('#') or '=' not in line: continue
  key,value=line.split('=',1); key=key.strip(); value=value.strip()
  if value[:1] in {'"',"'"}:
   try: parsed=shlex.split(value,posix=True); value=parsed[0] if parsed else ''
   except ValueError: value=value[1:-1] if len(value)>=2 else ''
  os.environ[key]=value
from sg_hostd.client_runtime import apply_all_clients
result=apply_all_clients(); print(json.dumps(result,ensure_ascii=False,indent=2,default=str))
if not result.get('ok'): raise SystemExit(1)
PY
)"; then log "$output"; else log "ПРЕДУПРЕЖДЕНИЕ: HTTPS включён, но не все клиентские runtime применились"; printf '%s\n' "$output" >&2; fi; xray_full_access; }
detect_public_ipv4(){ local token="" value=""; token="$(curl -fsS --connect-timeout 1 --max-time 2 -X PUT -H 'X-aws-ec2-metadata-token-ttl-seconds: 60' http://169.254.169.254/latest/api/token 2>/dev/null || true)"; [[ -z "$token" ]] || value="$(curl -fsS --connect-timeout 1 --max-time 2 -H "X-aws-ec2-metadata-token: $token" http://169.254.169.254/latest/meta-data/public-ipv4 2>/dev/null || true)"; [[ "$value" =~ ^([0-9]{1,3}\.){3}[0-9]{1,3}$ ]] || value="$(curl -4fsS --max-time 15 https://checkip.amazonaws.com 2>/dev/null | tr -d '[:space:]' || true)"; printf '%s' "$value"; }
configure_https(){ [[ -n "$HOST" ]] || fail "укажите домен"; HOST="${HOST,,}"; [[ "$HOST" =~ ^([A-Za-z0-9]([A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)+[A-Za-z]{2,63}$ ]] || fail "некорректное доменное имя"; local public_ip resolved cert_file key_file backup; SG_HTTPS_BACKUP_DIR=""; SG_HTTPS_COMMITTED=0; public_ip="$(detect_public_ipv4)"; resolved="$(getent ahostsv4 "$HOST" | awk '{print $1}' | sort -u || true)"; grep -Fxq "$public_ip" <<<"$resolved" || fail "A-запись домена ещё не указывает на этот сервер"; backup="$(create_backup)"; SG_HTTPS_BACKUP_DIR="$backup"; rollback(){ local rc=$?; trap - EXIT ERR INT TERM; if [[ "${SG_HTTPS_COMMITTED:-0}" -eq 0 && -n "$SG_HTTPS_BACKUP_DIR" ]]; then restore_backup "$SG_HTTPS_BACKUP_DIR"; nginx -t >/dev/null 2>&1 && systemctl reload nginx.service >/dev/null 2>&1 || true; fi; exit "$rc"; }; trap rollback EXIT ERR INT TERM; ensure_stream_include; cat > "$ACME_CONF" <<EOF
server { listen 80; listen [::]:80; server_name $HOST; location ^~ /.well-known/acme-challenge/ { root $ACME_ROOT; default_type text/plain; } location / { return 404; } }
EOF
ln -sfn "$ACME_CONF" "$ACME_LINK"; nginx -t; systemctl enable --now nginx.service; systemctl reload nginx.service; cert_file="/etc/letsencrypt/live/$HOST/fullchain.pem"; key_file="/etc/letsencrypt/live/$HOST/privkey.pem"; if [[ -s "$cert_file" && -s "$key_file" ]] && openssl x509 -checkend 604800 -noout -in "$cert_file" >/dev/null 2>&1; then log "Использую существующий сертификат"; else certbot certonly --webroot -w "$ACME_ROOT" --domain "$HOST" --register-unsafely-without-email --agree-tos --non-interactive --keep-until-expiring; fi; [[ -s "$cert_file" && -s "$key_file" ]] || fail "сертификат не создан"; write_stream_config "127.0.0.1:$PLACEHOLDER_TLS_INTERNAL_PORT"; write_https_site "$HOST" "$cert_file" "$key_file"; nginx -t; systemctl reload nginx.service; wait_backend; verify_https_contract "$HOST"; systemctl enable --now certbot.timer >/dev/null 2>&1 || true; cat > "$RENEW_HOOK" <<'EOF'
#!/usr/bin/env bash
set -Eeuo pipefail
exec /bin/bash /opt/sg-gateway/deploy/configure-panel-access.sh --mode refresh
EOF
chmod 0755 "$RENEW_HOOK"; write_state "$HOST" issue "HTTPS, fallback 443 и панель проверены" "$(basename "$backup")"; apply_client_runtime; SG_HTTPS_COMMITTED=1; trap - EXIT ERR INT TERM; log "HTTPS настроен: https://$HOST:$PUBLIC_PORT"; log "Заглушка: http://$HOST/ и https://$HOST/"; }
refresh_https(){ local domain cert key; domain="$(read_state_value domain)"; [[ -n "$domain" ]] || fail "HTTPS ещё не настроен"; cert="/etc/letsencrypt/live/$domain/fullchain.pem"; key="/etc/letsencrypt/live/$domain/privkey.pem"; [[ -s "$cert" && -s "$key" ]] || fail "файлы сертификата не найдены"; ensure_stream_include; write_stream_config "127.0.0.1:$PLACEHOLDER_TLS_INTERNAL_PORT"; write_https_site "$domain" "$cert" "$key"; nginx -t; systemctl reload nginx.service; wait_backend; verify_https_contract "$domain"; write_state "$domain" refresh "Сертификат, fallback 443 и Nginx проверены" "$(read_state_value backup)"; apply_client_runtime; log "HTTPS и fallback 443 обновлены"; }
renew_https(){ local domain="$(read_state_value domain)"; [[ -n "$domain" ]] || fail "HTTPS ещё не настроен"; certbot renew --cert-name "$domain" --non-interactive; refresh_https; apply_client_runtime; }
rollback_https(){ local latest current; latest="$(find "$BACKUP_ROOT" -mindepth 1 -maxdepth 1 -type d -name '*-panel-access' -printf '%f\n' | sort | tail -n 1 || true)"; [[ -n "$latest" ]] || fail "нет резервной конфигурации HTTPS"; current="$(create_backup)"; restore_backup "$BACKUP_ROOT/$latest"; if ! nginx -t || ! systemctl reload nginx.service; then restore_backup "$current"; nginx -t >/dev/null 2>&1 && systemctl reload nginx.service >/dev/null 2>&1 || true; fail "резервная конфигурация не принята"; fi; log "Восстановлена конфигурация $latest"; }
case "$MODE" in https) configure_https;; renew) renew_https;; rollback) rollback_https;; refresh) refresh_https;; esac
