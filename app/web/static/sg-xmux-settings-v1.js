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

    // Reality XHTTP mode is rendered by the main form as a hidden stream-one
    // value. TLS keeps its visible four-mode selector.
  };

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', ready, { once: true });
  } else {
    ready();
  }
})();