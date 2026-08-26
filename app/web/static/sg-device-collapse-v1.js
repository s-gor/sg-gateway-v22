/* SG-Gateway 0.1.0-022.06 dev — collapsed device cards + Mieru action polish */
(() => {
  'use strict';

  const interactiveSelector = 'button, a, input, select, textarea, label, form, details, summary, dialog';
  const protocolOrder = [
    'xray_reality_tcp',
    'xray_xhttp_reality',
    'xray_xhttp_tls',
    'xray_hysteria2',
    'amneziawg',
    'amneziawg3',
    'amneziawg31',
    'mihomo',
    'anytls',
    'tuic'
  ];

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
    document.querySelectorAll('.dv16-protocol-list').forEach(normalizeProtocolFieldset);

    const addDialog = document.getElementById('dv46-device-dialog');
    const picker = addDialog?.querySelector('.dv16-channel-picker');
    if (picker) picker.open = true;

    const recommended = addDialog?.querySelector('.dv16-recommended span');
    if (recommended) recommended.textContent = 'VLESS Reality TCP, Mieru и персональная SUB.';
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
