(() => {
  const ready = () => {
    const form = document.querySelector('[data-xmux-form]');
    if (form) {
      const details = form.querySelector('[data-xmux-extra]');
      const jsonInput = form.querySelector('[data-xmux-json]');
      const dialog = document.querySelector('[data-xmux-dialog]');
      const dialogTitle = dialog?.querySelector('[data-xmux-dialog-title]');
      const dialogPanels = dialog ? [...dialog.querySelectorAll('[data-xmux-dialog-panel]')] : [];
      const manualPreview = dialog?.querySelector('[data-xmux-manual-preview]');
      const modeTitles = {
        auto: 'Стандартный',
        reduced: 'Для РФ — уменьшенный',
        expert: 'Ручной',
      };

      const sync = () => {
        const selected = form.querySelector('input[name="xhttp_xmux_mode"]:checked');
        if (details && selected && selected.value === 'expert') {
          details.open = true;
        }
      };

      const closeDialog = () => {
        if (!dialog) return;
        if (typeof dialog.close === 'function' && dialog.open) {
          dialog.close();
        } else {
          dialog.removeAttribute('open');
        }
      };

      const syncManualPreview = () => {
        if (!manualPreview || !jsonInput) return;
        const raw = jsonInput.value.trim() || '{}';
        try {
          manualPreview.textContent = JSON.stringify(JSON.parse(raw), null, 2);
        } catch (_error) {
          manualPreview.textContent = raw;
        }
      };

      const showModeDetails = (mode) => {
        if (!dialog) return;
        dialogPanels.forEach((panel) => {
          panel.hidden = panel.dataset.xmuxDialogPanel !== mode;
        });
        if (dialogTitle) dialogTitle.textContent = modeTitles[mode] || 'XMUX';
        if (mode === 'expert') syncManualPreview();
        if (typeof dialog.showModal === 'function') {
          if (!dialog.open) dialog.showModal();
        } else {
          dialog.setAttribute('open', '');
        }
      };

      form.querySelectorAll('input[name="xhttp_xmux_mode"]').forEach((input) => {
        input.addEventListener('change', () => {
          sync();
          showModeDetails(input.value);
        });
        input.closest('.xmux1-mode')?.addEventListener('click', () => {
          // A checked radio does not emit change when its label is clicked again.
          // Still show its parameter window every time the user presses the mode.
          if (input.checked) showModeDetails(input.value);
        });
      });

      dialog?.querySelectorAll('[data-xmux-dialog-close]').forEach((button) => {
        button.addEventListener('click', closeDialog);
      });
      dialog?.addEventListener('click', (event) => {
        if (event.target === dialog) closeDialog();
      });
      jsonInput?.addEventListener('input', syncManualPreview);
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
