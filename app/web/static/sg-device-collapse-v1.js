/* SG-Gateway 0.1.0-022.06 dev — collapsed device cards + Mieru action polish */
(() => {
  'use strict';

  const interactiveSelector = 'button, a, input, select, textarea, label, form, details, summary, dialog';
  const protocolOrder = [
    'xray_reality_tcp',
    'xray_xhttp_reality',
    'amneziawg',
    'amneziawg3',
    'amneziawg31',
    'mihomo',
    'xray_xhttp_tls',
    'xray_hysteria2',
    'anytls',
    'tuic'
  ];

  const unifiedDialogCss = `
html body.page-clients .sg-unified-dialog.dv16-dialog{width:min(1120px,calc(100vw - 32px))!important;max-width:1120px!important;border:1px solid var(--sg-line)!important;border-radius:16px!important;background:var(--sg-panel)!important;color:var(--sg-text)!important;padding:0!important;box-shadow:var(--sg-shadow)!important}
html body.page-clients .sg-unified-dialog.dv16-dialog::backdrop{background:rgba(3,9,16,.75)!important;backdrop-filter:blur(5px)!important}
html body.page-clients .sg-unified-dialog .dv16-create-form{display:grid!important;gap:15px!important;max-height:min(820px,calc(100vh - 42px))!important;overflow:auto!important;margin:0!important;padding:21px!important}
html body.page-clients .sg-unified-dialog .dv16-dialog-head{display:flex!important;align-items:flex-start!important;justify-content:space-between!important;gap:18px!important;margin:0!important;padding:0!important;border:0!important;background:transparent!important}
html body.page-clients .sg-unified-dialog .dv16-dialog-head>div{min-width:0!important}
html body.page-clients .sg-unified-dialog .dv16-dialog-head>div>span{display:flex!important;align-items:center!important;gap:7px!important;color:var(--sg-blue)!important;font-size:9px!important;font-weight:850!important;letter-spacing:.16em!important;line-height:1.2!important}
html body.page-clients .sg-unified-dialog .dv16-dialog-head>div>span::before{content:""!important;display:block!important;width:5px!important;height:5px!important;flex:0 0 5px!important;border-radius:50%!important;background:var(--sg-blue)!important}
html body.page-clients .sg-unified-dialog .dv16-dialog-head h2{margin:6px 0 4px!important;color:var(--sg-text)!important;font-size:24px!important;line-height:1.2!important}
html body.page-clients .sg-unified-dialog .dv16-dialog-head p{max-width:760px!important;margin:0!important;color:var(--sg-muted)!important;font-size:10.5px!important;line-height:1.45!important}
html body.page-clients .sg-unified-dialog .dv16-dialog-close{display:grid!important;place-items:center!important;width:36px!important;min-width:36px!important;height:36px!important;min-height:36px!important;flex:0 0 36px!important;margin:0!important;padding:0!important;border:1px solid var(--sg-line)!important;border-radius:9px!important;background:var(--sg-panel-soft)!important;color:var(--sg-muted)!important;font-size:21px!important;line-height:1!important;cursor:pointer!important}
html body.page-clients .sg-unified-dialog .dv16-field{display:grid!important;gap:7px!important;min-width:0!important;margin:0!important}
html body.page-clients .sg-unified-dialog .dv16-field>span{color:var(--sg-text)!important;font-size:10px!important;font-weight:720!important}
html body.page-clients .sg-unified-dialog .dv16-field>input{width:100%!important;min-width:0!important;min-height:41px!important;box-sizing:border-box!important}
html body.page-clients .sg-unified-dialog .dv16-field>small{color:var(--sg-muted)!important;font-size:8.5px!important;line-height:1.4!important}
html body.page-clients .sg-unified-dialog .dv16-recommended{display:none!important}
html body.page-clients .sg-unified-dialog .dv16-protocol-list{display:grid!important;align-items:stretch!important;grid-auto-rows:1fr!important;gap:10px!important;min-width:0!important;margin:0!important;padding:0!important;border:0!important}
html body.page-clients .sg-unified-dialog .dv16-protocol-list>legend{grid-column:1/-1!important;margin:0 0 1px!important;padding:0!important;color:var(--sg-muted)!important;font-size:8px!important;font-weight:850!important;letter-spacing:.11em!important;text-transform:uppercase!important}
html body.page-clients .sg-unified-dialog .dv16-protocol-list>.dv16-protocol{position:relative!important;display:grid!important;grid-template-columns:18px minmax(0,1fr)!important;align-items:center!important;gap:10px!important;min-width:0!important;min-height:72px!important;height:100%!important;margin:0!important;padding:10px 12px!important;box-sizing:border-box!important;border:1px solid var(--sg-line)!important;border-radius:12px!important;background:color-mix(in srgb,var(--sg-panel-soft) 70%,transparent)!important;cursor:pointer!important;transition:border-color .15s ease,background .15s ease,box-shadow .15s ease!important}
html body.page-clients .sg-unified-dialog .dv16-protocol-list>.dv16-protocol>input{appearance:auto!important;display:block!important;position:static!important;width:17px!important;min-width:17px!important;height:17px!important;min-height:17px!important;margin:0!important;opacity:1!important;pointer-events:auto!important;accent-color:var(--sg-blue)!important}
html body.page-clients .sg-unified-dialog .dv16-protocol-list>.dv16-protocol>span{display:grid!important;gap:3px!important;min-width:0!important;min-height:0!important;height:auto!important;margin:0!important;padding:0!important;border:0!important;border-radius:0!important;background:transparent!important;box-shadow:none!important}
html body.page-clients .sg-unified-dialog .dv16-protocol-list>.dv16-protocol>span::before,html body.page-clients .sg-unified-dialog .dv16-protocol-list>.dv16-protocol>span::after{content:none!important;display:none!important}
html body.page-clients .sg-unified-dialog .dv16-protocol strong{overflow-wrap:anywhere!important;color:var(--sg-text)!important;font-size:11px!important;line-height:1.25!important}
html body.page-clients .sg-unified-dialog .dv16-protocol small{overflow-wrap:anywhere!important;color:var(--sg-muted)!important;font-size:9px!important;line-height:1.35!important}
html body.page-clients .sg-unified-dialog .dv16-protocol:has(>input:checked){border-color:color-mix(in srgb,var(--sg-blue) 70%,var(--sg-line))!important;background:color-mix(in srgb,var(--sg-blue) 10%,var(--sg-panel))!important;box-shadow:inset 3px 0 var(--sg-blue)!important}
html body.page-clients .sg-unified-dialog .dv16-protocol.is-locked,html body.page-clients .sg-unified-dialog .dv16-protocol:has(>input:disabled){opacity:.58!important;border-style:dashed!important;cursor:not-allowed!important}
html body.page-clients .sg-unified-dialog .dv16-dialog-actions{display:flex!important;flex-wrap:wrap!important;justify-content:flex-end!important;gap:8px!important;margin:4px 0 0!important;padding:0!important;border:0!important;background:transparent!important}
html body.page-clients .sg-unified-dialog .sg-awg-only-note{margin:0!important;border-radius:11px!important}
html body.page-clients .sg-unified-dialog .sg-awg-only-note.is-active{border-color:rgba(245,158,11,.92)!important;background:rgba(245,158,11,.19)!important;box-shadow:0 0 0 3px rgba(245,158,11,.12)!important}
@media(min-width:981px){html body.page-clients .sg-unified-dialog .dv16-protocol-list{grid-template-columns:repeat(5,minmax(0,1fr))!important}}
@media(min-width:721px) and (max-width:980px){html body.page-clients .sg-unified-dialog.dv16-dialog{width:min(760px,calc(100vw - 28px))!important;max-width:760px!important}html body.page-clients .sg-unified-dialog .dv16-protocol-list{grid-template-columns:repeat(2,minmax(0,1fr))!important}}
@media(max-width:720px){html body.page-clients .sg-unified-dialog.dv16-dialog{width:calc(100vw - 20px)!important;max-width:none!important}html body.page-clients .sg-unified-dialog .dv16-create-form{padding:16px!important}html body.page-clients .sg-unified-dialog .dv16-protocol-list{grid-template-columns:1fr!important}html body.page-clients .sg-unified-dialog .dv16-dialog-actions>.button{flex:1 1 150px!important;justify-content:center!important}}
`;

  function installUnifiedDialogStyle() {
    if (document.getElementById('sg-unified-client-device-dialog-v1')) return;
    const style = document.createElement('style');
    style.id = 'sg-unified-client-device-dialog-v1';
    style.textContent = unifiedDialogCss;
    document.head.appendChild(style);
  }

  function setExpanded(card, button, expanded) {
    card.classList.toggle('sg-device-expanded', expanded);
    card.classList.toggle('sg-device-collapsed', !expanded);
    button.setAttribute('aria-expanded', expanded ? 'true' : 'false');
    button.setAttribute('aria-label', expanded ? 'Свернуть устройство' : 'Развернуть устройство');
    button.title = expanded ? 'Свернуть устройство' : 'Развернуть устройство';
  }

  function setLabelTitle(label, title) {
    const target = label?.querySelector('strong');
    if (target) target.textContent = title;
  }

  function setAvailableNote(label, text) {
    const input = label?.querySelector('input[name="protocols"]');
    const note = label?.querySelector('small');
    if (input && note && !input.disabled) note.textContent = text;
  }

  function ensureAwgOnlyNotice(form) {
    if (!form || form.querySelector('[data-awg-only-note]')) return;
    const fieldset = form.querySelector('.dv16-protocol-list');
    if (!fieldset) return;
    const note = document.createElement('div');
    note.className = 'sg-awg-only-note';
    note.dataset.awgOnlyNote = '';
    note.setAttribute('role', 'status');
    note.setAttribute('aria-live', 'polite');
    note.textContent = 'При выборе только AWG-профилей подписка не создаётся. Используйте QR-коды или файлы конфигурации для каждого соединения.';
    fieldset.insertAdjacentElement('afterend', note);

    const awgOnlyValues = new Set(['amneziawg', 'amneziawg3', 'amneziawg31']);
    const sync = () => {
      const selected = [...form.querySelectorAll('input[type="checkbox"][name="protocols"]:checked')]
        .map(input => String(input.value || '').trim())
        .filter(value => value && value !== 'sgclient');
      note.classList.toggle('is-active', selected.length > 0 && selected.every(value => awgOnlyValues.has(value)));
    };
    form.addEventListener('change', event => {
      if (event.target?.matches('input[name="protocols"]')) sync();
    });
    sync();
  }

  function normalizeProtocolFieldset(fieldset) {
    if (!fieldset || fieldset.dataset.sgProtocolGridReady === '1') return;
    const dialog = fieldset.closest('dialog');
    const addMode = dialog?.id === 'dv46-device-dialog';
    const byValue = new Map();
    fieldset.querySelectorAll(':scope > label.dv16-protocol').forEach(label => {
      const input = label.querySelector('input[name="protocols"]');
      if (input) byValue.set(input.value, label);
    });

    setLabelTitle(byValue.get('amneziawg'), 'AmneziaWG 2.0');
    setLabelTitle(byValue.get('amneziawg3'), 'AmneziaWG 3.0');
    setLabelTitle(byValue.get('amneziawg31'), 'AmneziaWG 3.1');

    if (addMode) {
      setAvailableNote(byValue.get('xray_reality_tcp'), 'Отдельный профиль и QR');
      setAvailableNote(byValue.get('xray_xhttp_reality'), 'Отдельный профиль и QR');
      setAvailableNote(byValue.get('xray_xhttp_tls'), 'Отдельный профиль и QR');
      setAvailableNote(byValue.get('xray_hysteria2'), 'Отдельный профиль и QR');
      setAvailableNote(byValue.get('amneziawg'), 'UDP 585 · отдельная конфигурация и QR');
      setAvailableNote(byValue.get('amneziawg3'), 'UDP 586 · userspace-конфигурация и QR');
      setAvailableNote(byValue.get('amneziawg31'), 'UDP 587 · userspace-конфигурация');
      setAvailableNote(byValue.get('mihomo'), 'Mieru-ссылка, Router / ZB и JSON для iPhone');
      setAvailableNote(byValue.get('anytls'), 'Отдельный TLS-профиль и QR');
      setAvailableNote(byValue.get('tuic'), 'Отдельный QUIC/UDP-профиль и QR');
    }

    protocolOrder.forEach(value => {
      const label = byValue.get(value);
      if (label) fieldset.appendChild(label);
    });

    fieldset.dataset.sgProtocolGridReady = '1';
  }

  function normalizeProtocolPickers() {
    installUnifiedDialogStyle();

    const addDialog = document.getElementById('dv46-device-dialog');
    if (addDialog) {
      addDialog.classList.add('sg-unified-dialog');
      addDialog.querySelector('.dv16-recommended')?.remove();
      const picker = addDialog.querySelector('details.dv16-channel-picker');
      if (picker) picker.replaceWith(...picker.childNodes);
    }

    document.querySelectorAll('#dv-edit-client-dialog, [id^="dv-edit-device-"]').forEach(dialog => {
      dialog.classList.add('sg-unified-dialog');
    });

    document.querySelectorAll('.dv16-protocol-list').forEach(fieldset => {
      normalizeProtocolFieldset(fieldset);
      ensureAwgOnlyNotice(fieldset.closest('form'));
    });
  }

  function prepareDisableActions() {
    document.querySelectorAll('.dv16-device-controls .button, .dv16-heading-actions .button').forEach(button => {
      const text = button.textContent.replace(/\s+/g, ' ').trim();
      if (!text.toLowerCase().startsWith('отключить')) return;

      const form = button.closest('form');
      if (!form) return;

      const card = button.closest('.dv16-device');
      if (card) {
        const deviceName = card.querySelector('.dv16-device-title h2')?.textContent.trim() || 'устройство';
        form.dataset.sgConfirm = `Отключить «${deviceName}»? Подключения этого устройства перестанут работать до повторного включения.`;
        form.dataset.sgConfirmTitle = 'Отключить устройство';
        form.dataset.sgConfirmButton = 'Отключить';
        form.dataset.sgConfirmKicker = 'Защита от случайного отключения';
        form.dataset.sgConfirmTone = 'warning';
        button.classList.add('sg-warm-action');
        return;
      }

      const clientName = document.querySelector('.dv16-heading h1')?.textContent.trim() || 'клиента';
      form.dataset.sgConfirm = `Отключить клиента «${clientName}»? Все его устройства и подключения станут недоступны до повторного включения.`;
      form.dataset.sgConfirmTitle = 'Отключить клиента';
      form.dataset.sgConfirmButton = 'Отключить';
      form.dataset.sgConfirmKicker = 'Защита от случайного отключения';
      form.dataset.sgConfirmTone = 'warning';
    });
  }

  function smartQr(details, title, subtitle = 'Сканируйте в приложении') {
    const popover = details?.querySelector('.dv16-qr-popover');
    if (!popover || popover.querySelector('.sg-smart-qr-meta')) return;
    const meta = document.createElement('div');
    meta.className = 'sg-smart-qr-meta';
    const strong = document.createElement('strong');
    strong.textContent = title;
    const small = document.createElement('small');
    small.textContent = subtitle;
    meta.append(strong, small);
    const image = popover.querySelector('img');
    popover.insertBefore(meta, image || null);
  }

  function routerQrUrl(mieruQr) {
    const source = mieruQr?.querySelector('img')?.getAttribute('src') || '';
    if (!source) return '';
    return source.replace(/\/protocols\/mieru\/qr(?:\?.*)?$/, '/mieru-router/qr');
  }

  function createRouterQr(mieruQr) {
    const src = routerQrUrl(mieruQr);
    if (!src || src === mieruQr?.querySelector('img')?.getAttribute('src')) return null;
    const details = document.createElement('details');
    details.className = 'dv16-qr sg-mieru-router-qr';
    details.innerHTML = `
      <summary class="button">QR · Router / ZB</summary>
      <div class="dv16-qr-popover">
        <button type="button" aria-label="Закрыть QR · Router / ZB">×</button>
        <img src="${src}" alt="QR Mieru · Router / ZB">
      </div>`;
    details.querySelector('.dv16-qr-popover > button')?.addEventListener('click', () => details.removeAttribute('open'));
    smartQr(details, 'Router / ZB');
    return details;
  }

  function normalizeMieruActions() {
    document.querySelectorAll('.dv16-technical-row').forEach(row => {
      const routerButton = row.querySelector('[data-mieru-router-source]');
      if (!routerButton || row.dataset.sgMieruActionsReady === '1') return;
      const actions = row.querySelector('.dv16-technical-actions');
      if (!actions) return;

      const buttons = Array.from(actions.querySelectorAll(':scope > button'));
      const qrs = Array.from(actions.querySelectorAll(':scope > details.dv16-qr'));
      const links = Array.from(actions.querySelectorAll(':scope > a.button'));

      const linkButton = buttons.find(button => /Скопировать ссылку/i.test(button.textContent)) || buttons.find(button => button.dataset.copyValue);
      const iphoneButton = buttons.find(button => /iPhone/i.test(button.textContent));
      const mieruQr = qrs.find(details => /Mieru/i.test(details.querySelector('summary')?.textContent || '') && !/iPhone/i.test(details.querySelector('summary')?.textContent || '')) || qrs[0];
      const iphoneQr = qrs.find(details => /iPhone/i.test(details.querySelector('summary')?.textContent || ''));
      const downloadLink = links.find(link => /Скачать ссылку/i.test(link.textContent));
      const jsonDownload = links.find(link => /Mieru JSON/i.test(link.textContent));
      const yamlDownload = links.find(link => /Mihomo YAML/i.test(link.textContent));

      if (linkButton) linkButton.textContent = 'Ссылка';
      routerButton.textContent = 'Router / ZB';
      if (iphoneButton) iphoneButton.textContent = 'JSON · iPhone';

      if (mieruQr) {
        const summary = mieruQr.querySelector('summary');
        if (summary) summary.textContent = 'QR · Mieru';
        smartQr(mieruQr, 'Mieru');
      }
      if (iphoneQr) {
        const summary = iphoneQr.querySelector('summary');
        if (summary) summary.textContent = 'QR · iPhone';
        smartQr(iphoneQr, 'iPhone JSON');
      }

      const routerQr = createRouterQr(mieruQr);
      const advancedItems = [downloadLink, jsonDownload, yamlDownload].filter(Boolean);

      [linkButton, mieruQr, routerButton, routerQr, iphoneButton, iphoneQr, ...advancedItems].filter(Boolean).forEach(item => actions.appendChild(item));
      row.dataset.sgMieruActionsReady = '1';
    });
  }

  function markExporterErrors() {
    document.querySelectorAll('.dv16-technical-row.state-error').forEach(row => {
      const status = row.querySelector(':scope > div:first-child small');
      if (status) status.textContent = 'Ошибка генерации';
      const actions = row.querySelector('.dv16-technical-actions');
      if (!actions || actions.querySelector('.sg-export-error')) return;
      const note = document.createElement('span');
      note.className = 'sg-export-error';
      note.textContent = 'Остальные профили устройства доступны';
      actions.appendChild(note);
    });
  }

  function initDevice(card) {
    if (card.dataset.sgCollapseReady === '1') return;

    const head = card.querySelector(':scope > .dv16-device-head');
    const controls = head?.querySelector('.dv16-device-controls');
    if (!head || !controls) return;

    let button = controls.querySelector('.sg-device-collapse-toggle');
    if (!button) {
      button = document.createElement('button');
      button.type = 'button';
      button.className = 'button sg-device-collapse-toggle';
      button.innerHTML = '<span aria-hidden="true">⌄</span>';
      controls.appendChild(button);
    }

    setExpanded(card, button, false);
    card.dataset.sgCollapseReady = '1';

    button.addEventListener('click', event => {
      event.preventDefault();
      event.stopPropagation();
      setExpanded(card, button, card.classList.contains('sg-device-collapsed'));
    });

    head.addEventListener('click', event => {
      if (event.target.closest(interactiveSelector)) return;
      setExpanded(card, button, card.classList.contains('sg-device-collapsed'));
    });

    head.addEventListener('keydown', event => {
      if (event.target.closest(interactiveSelector)) return;
      if (event.key !== 'Enter' && event.key !== ' ') return;
      event.preventDefault();
      setExpanded(card, button, card.classList.contains('sg-device-collapsed'));
    });

    const title = head.querySelector('.dv16-device-title');
    if (title) {
      title.tabIndex = 0;
      title.setAttribute('role', 'button');
      title.setAttribute('aria-label', 'Развернуть или свернуть устройство');
    }
  }

  function initAll() {
    normalizeProtocolPickers();
    document.querySelectorAll('.dv16-devices > .dv16-device').forEach(initDevice);
    prepareDisableActions();
    normalizeMieruActions();
    markExporterErrors();

    const hash = String(location.hash || '');
    if (hash.startsWith('#device-')) {
      const target = document.querySelector(hash);
      const button = target?.querySelector('.sg-device-collapse-toggle');
      if (target && button) setExpanded(target, button, true);
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initAll, { once: true });
  } else {
    initAll();
  }
})();
