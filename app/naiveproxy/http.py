from __future__ import annotations

from flask import jsonify, request

from app.connections.settings import get_connection_settings, update_connection_settings
from app.hostd.client import run_hostd_command
from app.naiveproxy.integration import _restore_connection_settings, reserved_ports
from app.naiveproxy.runtime import DEFAULT_PORT, NaiveProxyError, validate_port
from app.security.tls import overview as tls_overview


_COMPACT_STYLESHEET = (
    '<link rel="stylesheet" href="/static/sg-compact-protocol-cards-v1.css">'
)

_SETTINGS_PANEL = r"""
<article id="sg-naiveproxy-settings"
         class="xps2-parameter-row is-visible xps2-naiveproxy-card"
         data-naiveproxy-panel>
  <div class="xps2-parameter-title">
    <strong>NaiveProxy</strong>
    <span>HTTPS Forward Proxy · TLS</span>
  </div>
  <div class="xps2-naiveproxy-meta">
    <span>HTTPS-домен</span>
    <strong data-naive-host>—</strong>
  </div>
  <div class="xps2-naiveproxy-action">
    <span class="cnv1-engine-status warning" data-naive-state><span></span>Проверка…</span>
    <button class="button primary" type="button" data-naive-submit>Проверить и применить</button>
  </div>
  <span class="xps2-naiveproxy-message" data-naive-message aria-live="polite"></span>
</article>
<script>
(() => {
  const root = document.querySelector('[data-naiveproxy-panel]');
  if (!root) return;
  const parameterList = document.querySelector('.xps2-parameter-list');
  if (parameterList && root.parentElement !== parameterList) {
    parameterList.appendChild(root);
  }

  const host = root.querySelector('[data-naive-host]');
  const state = root.querySelector('[data-naive-state]');
  const message = root.querySelector('[data-naive-message]');
  const submit = root.querySelector('[data-naive-submit]');
  let activePort = 8447;

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
    activePort = Number(payload.port || payload.default_port || 8447);
    host.textContent = payload.host || 'HTTPS не настроен';
    const healthy = payload.status === 'ok' && runtime.ok === true;
    state.classList.toggle('success', healthy);
    state.classList.toggle('warning', !healthy);
    state.lastChild.textContent = healthy ? 'Работает' : 'Не настроен';
  };

  submit.addEventListener('click', async () => {
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
        body: JSON.stringify({port: Number(activePort)})
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
            payload = request.get_json(silent=True)
            if not isinstance(payload, dict):
                return jsonify({
                    "ok": False,
                    "message": "NaiveProxy settings require an application/json request",
                }), 415
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
                if str(previous.host or "").strip():
                    restored = update_connection_settings(
                        "naiveproxy",
                        previous.host,
                        previous.port,
                        dict(previous.config),
                    )
                else:
                    restored = _restore_connection_settings(previous)
                if not restored:
                    return jsonify({
                        "ok": False,
                        "message": (
                            f"{result.message}. Восстановить предыдущие "
                            "настройки в БД не удалось"
                        ),
                        "runtime": result.payload,
                        "settings_rollback": False,
                    }), 500
                return jsonify({
                    "ok": False,
                    "message": (
                        f"{result.message}. Предыдущие настройки в БД восстановлены"
                    ),
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
        note = (
            "HTTPS-прокси · отдельная ссылка"
            if ready
            else "Требуется HTTPS в Security"
        )
        option = (
            f'<label class="cv10-protocol{locked}">'
            f'<input type="checkbox" name="protocols" value="naiveproxy"{disabled}>'
            f'<span><strong>NaiveProxy</strong><small>{note}</small></span></label>\n      '
        )
        body = body.replace(marker, option + marker)

    if request.endpoint == "connections":
        if _COMPACT_STYLESHEET not in body and "</head>" in body:
            body = body.replace(
                "</head>",
                f"  {_COMPACT_STYLESHEET}\n</head>",
                1,
            )
        if 'id="sg-naiveproxy-settings"' not in body:
            script_marker = "<script>"
            head, separator, tail = body.rpartition(script_marker)
            body = (
                head + _SETTINGS_PANEL + separator + tail
                if separator
                else body + _SETTINGS_PANEL
            )

    response.set_data(body)
    return response
