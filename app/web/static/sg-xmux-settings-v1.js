(() => {
  const ready = () => {
    const form = document.querySelector('[data-xmux-form]');
    if (form) {
      const details = form.querySelector('[data-xmux-extra]');
      const sync = () => {
        const selected = form.querySelector('input[name="xhttp_xmux_mode"]:checked');
        if (details && selected && selected.value === 'expert') {
          details.open = true;
        }
      };
      form.querySelectorAll('input[name="xhttp_xmux_mode"]').forEach((node) => {
        node.addEventListener('change', sync);
      });
      sync();
    }

    // SG-Panel contract: Reality XHTTP client mode is fixed stream-one.
    // The server remains auto; TLS keeps the existing four-mode selector.
    const realityMode = document.querySelector('select[name="xhttp_reality_mode"]');
    if (realityMode) {
      realityMode.value = 'stream-one';
      const label = realityMode.closest('label');
      if (label && !document.querySelector('[data-xmux-reality-fixed]')) {
        const fixed = document.createElement('div');
        fixed.className = 'xps2-flow-field xmux1-fixed-mode';
        fixed.dataset.xmuxRealityFixed = '1';
        fixed.innerHTML = '<span>XHTTP mode клиента</span><strong>Stream One · stream-one</strong><small>Фиксировано как в SG-Panel. Серверный XHTTP mode остаётся auto.</small>';

        // Replacing the visible select must not remove the value from the main
        // Xray Apply form. Keep the fixed client mode in the POST payload.
        const hidden = document.createElement('input');
        hidden.type = 'hidden';
        hidden.name = 'xhttp_reality_mode';
        hidden.value = 'stream-one';
        fixed.appendChild(hidden);

        label.replaceWith(fixed);
      } else {
        realityMode.disabled = true;
      }
    }
  };

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', ready, { once: true });
  } else {
    ready();
  }
})();