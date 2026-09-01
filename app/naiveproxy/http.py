from __future__ import annotations

from flask import jsonify, request

from app.connections.settings import get_connection_settings, update_connection_settings
from app.hostd.client import run_hostd_command
from app.naiveproxy.integration import reserved_ports
from app.naiveproxy.runtime import DEFAULT_PORT, NaiveProxyError, validate_port
from app.security.tls import overview as tls_overview


_SETTINGS_PANEL = r"""
<section id="sg-naiveproxy-settings" class="cnv1-engines" data-naiveproxy-panel>
  <article class="cnv1-engine-card sg-ljd-card">
    <header class="cnv1-engine-head">
      <div class="cnv1-engine-title">
        <div>
          <div class="cnv1-card-kicker">HTTPS FORWARD PROXY · ОТДЕЛЬНЫЙ LISTENER</div>
          <h2>NaiveProxy</h2>
          <p>Reality остаётся на TCP 443. NaiveProxy использует собственный проверяемый порт.</p>
        </div>
      </div>
      <span class="cnv1-engine-status warning" data-naive-state><span></span>Проверка…</span>
    </header>

    <section class="cnv1-endpoint-card sg-ljd-nested">
      <div class="cnv1-endpoint-main">
        <div>
          <span>HTTPS-ДОМЕН</span>
          <strong data-naive-host>—</strong>
          <small data-naive-runtime>Runtime ещё не проверен</small>
        </div>
      </div>
    </section>

    <form data-naive-form>
      <section class="xps2-parameters sg-ljd-nested">
        <div class="xps2-parameter-list">
          <article class="xps2-parameter-row is-visible">
            <div class="xps2-parameter-title">
              <strong>TCP-порт NaiveProxy</strong>
              <span>1–65535. Конфликты с listener SG-Gateway и занятыми портами блокируются до применения.</span>
            </div>
            <label class="xps2-field-mode">
              <span>Порт</span>
              <input data-naive-port name="port" type="number" min="1" max="65535" inputmode="numeric" required value="8447">
              <small>По умолчанию 8447. Firewall меняется только после успешной проверки Caddy.</small>
            </label>
          </article>
        </div>
      </section>
      <div class="xps2-top-actions">
        <button class="button primary" type="submit" data-naive-submit>Проверить и применить</button>
        <span data-naive-message aria-live="polite"></span>
      </div>
    </form>
  </article>
</section>
<script>
(() => {
  const root = document.querySelector('[data-naiveproxy-panel]');
  if (!root) return;
  const form = root.querySelector('[data-naive-form]');
  const port = root.querySelector('[data-naive-port]');
  const host = root.querySelector('[data-naive-host]');
  const state = root.querySelector('[data-naive-state]');
  const runtimeText = root.querySelector('[data-naive-runtime]');
  const message = root.querySelector('[data-naive-message]');
  const submit = root.querySelector('[data-naive-submit]');

  const setMessage = (text, error = false) => {
    message.textContent = text || '';
    message.dataset.tone = error ? 'error' : 'ok';
  };

  const load = async () => {
    const response = await fetch('/api/naiveproxy/status', {
      credentials: 'same-origin',
      headers: {'X-Requested-With': 'XMLHttpRequest'}
    });
    const payload = await response.json();
    const runtime = payload.runtime || {};
    port.value = String(payload.port || payload.default_port || 8447);
    host.textContent = payload.host || 'HTTPS не настроен';
    const healthy = payload.status === 'ok' && runtime.ok === true;
    state.classList.toggle('success', healthy);
    state.classList.toggle('warning', !healthy);
    state.lastChild.textContent = healthy ? 'Работает' : 'Не запущен';
    const version = runtime.runtime_version || runtime.runtime_release || 'runtime не установлен';
    const checksum = runtime.checksum_ok === true ? 'SHA проверен' : 'SHA не подтверждён';
    const listener = runtime.listener?.owned_by_service === true ? 'listener подтверждён' : 'listener не подтверждён';
    runtimeText.textContent = `${version} · ${checksum} · ${listener}`;
  };

  form.addEventListener('submit', async event => {
    event.preventDefault();
    submit.disabled = true;
    setMessage('Проверка и применение…');
    try {
      const response = await fetch('/api/naiveproxy/settings', {
        method: 'POST',
        credentials: 'same-origin',
        headers: {
          'Content-Type': 'application/json',
          'X-Requested-With': 'XMLHttpRequest'
        },
        body: JSON.stringify({port: Number(port.value)})
      });
      const payload = await response.json();
      if (!response.ok || payload.ok !== true) {
        throw new Error(payload.message || 'Настройки не применены');
      }
      setMessage(payload.message || 'NaiveProxy применён.');
      await load();
    } catch (error) {
      setMessage(error.message || 'Настройки не применены', true);
    } finally {
      submit.disabled = false;
    }
  });

  load().catch(error => setMessage(error.message || 'Статус недоступен', true));
})();
</script>
"""


def register_naiveproxy_http(app) -> None:
    if not getattr(app, "_naiveproxy_ui_installed", False):
        app.after_request(_inject_naiveproxy_ui)
        app._naiveproxy_ui_installed = True
    if "naiveproxy_status" not in app.view_functions:
        def status():
            settings = get_connection_settings("naiveproxy")
            result = run_hostd_command("naiveproxy.status", timeout=10)
            return jsonify({
                "engine": "naiveproxy",
                "host": settings.host,
                "port": settings.port,
                "default_port": DEFAULT_PORT,
                "runtime": result.payload,
                "status": result.status,
                "message": result.message,
            }), 200 if result.status == "ok" else 503

        app.add_url_rule(
            "/api/naiveproxy/status",
            endpoint="naiveproxy_status",
            view_func=status,
            methods=["GET"],
        )

    if "naiveproxy_settings" not in app.view_functions:
        def settings_update():
            payload = request.get_json(silent=True) or request.form
            tls = tls_overview()
            domain = str(tls.get("domain") or "").strip()
            if not tls.get("https_ready") or not domain:
                return jsonify({"ok": False, "message": "Сначала настройте HTTPS в Security"}), 409
            try:
                port = validate_port(payload.get("port", DEFAULT_PORT), reserved_ports())
            except NaiveProxyError as exc:
                return jsonify({"ok": False, "message": str(exc)}), 400
            config = {
                "domain": domain,
                "certificate_path": str(tls.get("certificate_path") or ""),
                "private_key_path": f"/etc/letsencrypt/live/{domain}/privkey.pem",
            }
            previous = get_connection_settings("naiveproxy")
            if not update_connection_settings("naiveproxy", domain, port, config):
                return jsonify({"ok": False, "message": "Настройки NaiveProxy отклонены"}), 400
            result = run_hostd_command("naiveproxy.sync", timeout=60)
            if result.status != "ok":
                restored = update_connection_settings(
                    "naiveproxy",
                    previous.host,
                    previous.port,
                    dict(previous.config),
                )
                if not restored:
                    return jsonify({
                        "ok": False,
                        "message": (
                            f"{result.message}. Runtime откатился, но восстановить "
                            "предыдущие настройки в БД не удалось"
                        ),
                        "runtime": result.payload,
                        "settings_rollback": False,
                    }), 500
                return jsonify({
                    "ok": False,
                    "message": f"{result.message}. Предыдущие настройки восстановлены",
                    "runtime": result.payload,
                    "settings_rollback": True,
                }), 503
            return jsonify({"ok": True, "message": result.message, "runtime": result.payload}), 200

        app.add_url_rule(
            "/api/naiveproxy/settings",
            endpoint="naiveproxy_settings",
            view_func=settings_update,
            methods=["POST"],
        )


def _inject_naiveproxy_ui(response):
    if response.direct_passthrough or response.mimetype != "text/html":
        return response
    body = response.get_data(as_text=True)
    marker = "<!-- SG_PROTOCOL_ORDER_END -->"
    if marker in body and 'value="naiveproxy"' not in body:
        tls = tls_overview()
        ready = bool(tls.get("https_ready"))
        disabled = "" if ready else " disabled"
        locked = "" if ready else " is-locked"
        try:
            configured_port = int(get_connection_settings("naiveproxy").port or DEFAULT_PORT)
        except (TypeError, ValueError):
            configured_port = DEFAULT_PORT
        note = (
            f"HTTPS-прокси · отдельная ссылка · TCP {configured_port}"
            if ready
            else "Требуется HTTPS в Security"
        )
        option = (
            f'<label class="cv10-protocol{locked}">'
            f'<input type="checkbox" name="protocols" value="naiveproxy"{disabled}>'
            f'<span><strong>NaiveProxy</strong><small>{note}</small></span></label>\n      '
        )
        body = body.replace(marker, option + marker)

    if request.endpoint == "connections" and 'id="sg-naiveproxy-settings"' not in body:
        script_marker = "<script>"
        head, separator, tail = body.rpartition(script_marker)
        body = (
            head + _SETTINGS_PANEL + separator + tail
            if separator
            else body + _SETTINGS_PANEL
        )

    response.set_data(body)
    return response
