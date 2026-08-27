/* SG_AWG_ONLY_NOTICE_V1_JS */
(() => {
  'use strict';

  const awgOnlyValues = new Set(['amneziawg', 'amneziawg3', 'amneziawg31']);

  function initializeNotice(note) {
    const form = note.closest('form');
    if (!form || note.dataset.awgOnlyReady === '1') return;
    note.dataset.awgOnlyReady = '1';

    const syncAwgOnlyNotice = () => {
      const selected = [...form.querySelectorAll(
        'input[type="checkbox"][name="protocols"]:checked'
      )]
        .map(input => String(input.value || '').trim())
        .filter(value => value && value !== 'sgclient');
      const isAwgOnly = (
        selected.length > 0
        && selected.every(value => awgOnlyValues.has(value))
      );
      note.classList.toggle('is-active', isAwgOnly);
    };

    form.addEventListener('change', event => {
      if (event.target?.matches('input[name="protocols"]')) {
        syncAwgOnlyNotice();
      }
    });
    syncAwgOnlyNotice();
  }

  function initialize() {
    document.querySelectorAll('[data-awg-only-note]').forEach(initializeNotice);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initialize, {once: true});
  } else {
    initialize();
  }
})();
