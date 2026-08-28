(() => {
  const configureFingerprintMenu = () => {
    const fingerprint = document.querySelector(
      '[data-fingerprint-panel] select[name="fingerprint"]'
    );
    if (!fingerprint) return;

    const styles = getComputedStyle(fingerprint);
    const channels = (styles.backgroundColor.match(/\d+(?:\.\d+)?/g) || [])
      .slice(0, 3)
      .map(Number);
    const luminance = channels.length === 3
      ? (0.2126 * channels[0]) + (0.7152 * channels[1]) + (0.0722 * channels[2])
      : 0;

    fingerprint.style.colorScheme = luminance < 128 ? 'dark' : 'light';
    fingerprint.querySelectorAll('option, optgroup').forEach((item) => {
      item.style.backgroundColor = styles.backgroundColor;
      item.style.color = styles.color;
    });
  };

  const configureCompactRealityPanel = () => {
    const form = document.querySelector(
      '.cnv1-engine-xray form[action$="/connections/xray"]'
    );
    if (!form) return;

    const grid = form.querySelector('.cnv1-form-grid');
    if (!grid) return;

    form.classList.add('xray-reality-compact');
    grid.classList.add('xray-reality-compact-grid');

    const hostField = grid.querySelector('input[name="host"]');
    const portField = grid.querySelector('input[name="port"]');
    hostField.closest('label')?.remove();
    portField.closest('label')?.remove();

    const serverName = grid.querySelector('input[name="server_name"]');
    const serverNameLabel = serverName?.closest('label');
    serverNameLabel?.classList.add('xray-reality-sni');

    const details = form.closest('details');
    const summaryTitle = details?.querySelector(':scope > summary span:first-child');
    if (summaryTitle) summaryTitle.textContent = 'Reality SNI и ключи';

    const addCopyAction = (field, areaClass) => {
      if (!field) return;

      field.readOnly = true;
      field.removeAttribute('name');
      field.setAttribute('aria-readonly', 'true');
      field.dataset.serverManaged = '1';
      field.title = 'Значение управляется сервером';
      if (field.tagName === 'TEXTAREA') field.rows = 1;

      const label = field.closest('label');
      if (!label) return;
      label.classList.add('xray-reality-readonly', areaClass);
      label.querySelector('[data-server-managed-note]')?.remove();

      const valueRow = document.createElement('div');
      valueRow.className = 'xray-reality-value-row';
      field.replaceWith(valueRow);
      valueRow.append(field);

      const copyButton = document.createElement('button');
      copyButton.type = 'button';
      copyButton.className = 'button xray-reality-copy';
      copyButton.textContent = 'Копировать';
      copyButton.addEventListener('click', async () => {
        const original = copyButton.textContent;
        try {
          await navigator.clipboard.writeText(field.value);
          copyButton.textContent = 'Скопировано';
        } catch (_error) {
          field.focus();
          field.select();
          document.execCommand('copy');
          copyButton.textContent = 'Скопировано';
        }
        window.setTimeout(() => {
          copyButton.textContent = original;
        }, 1400);
      });
      valueRow.append(copyButton);
    };

    addCopyAction(
      grid.querySelector('textarea[name="public_key"]'),
      'xray-reality-public'
    );
    addCopyAction(
      grid.querySelector('input[name="short_id"]'),
      'xray-reality-short'
    );

    const footer = form.querySelector('.cnv1-form-actions');
    footer?.classList.add('xray-reality-actions');
    const footerText = footer?.querySelector('span');
    if (footerText) footerText.textContent = 'Изменяется только Reality SNI.';
    const submitButton = footer?.querySelector('button[type="submit"]');
    if (submitButton) submitButton.textContent = 'Сохранить SNI';
  };

  const ready = () => {
    configureFingerprintMenu();
    configureCompactRealityPanel();

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

      if (details) details.open = false;

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
