/* SG-Gateway 0.1.0-021.9 — collapsed device cards, clean single-surface V3 */
(() => {
  'use strict';

  const interactiveSelector = 'button, a, input, select, textarea, label, form, details, summary, dialog';

  function setExpanded(card, button, expanded) {
    card.classList.toggle('sg-device-collapsed', !expanded);
    button.setAttribute('aria-expanded', expanded ? 'true' : 'false');
    button.setAttribute('aria-label', expanded ? 'Свернуть устройство' : 'Развернуть устройство');
    button.title = expanded ? 'Свернуть устройство' : 'Развернуть устройство';
  }

  function initDevice(card) {
    if (card.dataset.sgCollapseReady === '1') return;

    const head = card.querySelector(':scope > .dv16-device-head');
    const controls = head?.querySelector('.dv16-device-controls');
    if (!head || !controls) return;

    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'button sg-device-collapse-toggle';
    button.innerHTML = '<span aria-hidden="true">⌄</span>';
    controls.appendChild(button);

    card.dataset.sgCollapseReady = '1';
    setExpanded(card, button, false);

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
    document.querySelectorAll('.dv16-devices > .dv16-device').forEach(initDevice);

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
