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

  const ensureXrayTwoRowStyles = () => {
    if (document.getElementById('xray-two-row-styles')) return;

    const style = document.createElement('style');
    style.id = 'xray-two-row-styles';
    style.textContent = `
      .cnv1-engine-xray .xray-settings-primary {
        display: grid !important;
        grid-template-columns: minmax(0, 1fr) minmax(0, 1fr) auto !important;
        grid-template-areas: "fingerprint sni action" !important;
        align-items: end;
        gap: 10px 12px;
        padding: 12px 14px;
      }
      .cnv1-engine-xray .xray-settings-primary .xps2-parameter-title {
        display: none !important;
      }
      .cnv1-engine-xray .xray-settings-primary > .xps2-field-mode {
        grid-area: fingerprint !important;
      }
      .cnv1-engine-xray .xray-settings-primary > .xray-reality-sni {
        display: grid;
        grid-area: sni;
        min-width: 0;
        gap: 5px;
      }
      .cnv1-engine-xray .xray-settings-primary > label > span {
        display: block !important;
        color: var(--sg-muted);
        font-size: 9.5px;
        font-weight: 800;
        letter-spacing: .025em;
      }
      .cnv1-engine-xray .xray-settings-primary .xps2-field-mode > small {
        display: none !important;
      }
      .cnv1-engine-xray .xray-settings-primary select,
      .cnv1-engine-xray .xray-settings-primary input {
        width: 100%;
        min-width: 0;
        min-height: 42px;
      }
      .cnv1-engine-xray .xray-settings-primary > .xray-reality-save {
        grid-area: action;
        min-height: 42px;
        padding-inline: 16px;
        white-space: nowrap;
      }
      .cnv1-engine-xray .xray-settings-identity {
        display: grid !important;
        grid-template-columns: minmax(0, 1.45fr) minmax(260px, .55fr) !important;
        grid-template-areas: none !important;
        align-items: end;
        gap: 10px 14px;
        padding: 12px 14px;
      }
      .cnv1-engine-xray .xray-settings-identity > label {
        display: grid;
        min-width: 0;
        gap: 5px;
      }
      .cnv1-engine-xray .xray-settings-identity > label > span {
        color: var(--sg-muted);
        font-size: 9.5px;
        font-weight: 800;
        letter-spacing: .025em;
      }
      .cnv1-engine-xray .xray-reality-value-row {
        display: grid;
        grid-template-columns: minmax(0, 1fr) 42px;
        align-items: stretch;
        min-width: 0;
        gap: 8px;
      }
      .cnv1-engine-xray .xray-reality-value-row input,
      .cnv1-engine-xray .xray-reality-value-row textarea {
        width: 100%;
        min-width: 0;
        min-height: 42px;
        height: 42px;
        resize: none;
        overflow: hidden;
        white-space: nowrap;
        cursor: text;
        opacity: .92;
        font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
      }
      .cnv1-engine-xray .xray-copy-icon {
        display: inline-grid;
        width: 42px;
        min-width: 42px;
        min-height: 42px;
        place-items: center;
        padding: 0;
        font-size: 19px;
        line-height: 1;
      }
      .cnv1-engine-xray .xray-reality-form-anchor {
        display: none !important;
      }
      @media (max-width: 900px) {
        .cnv1-engine-xray .xray-settings-primary {
          grid-template-columns: minmax(0, 1fr) auto !important;
          grid-template-areas:
            "fingerprint fingerprint"
            "sni action" !important;
        }
        .cnv1-engine-xray .xray-settings-identity {
          grid-template-columns: minmax(0, 1fr) !important;
        }
      }
      @media (max-width: 620px) {
        .cnv1-engine-xray .xray-settings-primary {
          grid-template-columns: minmax(0, 1fr) !important;
          grid-template-areas:
            "fingerprint"
            "sni"
            "action" !important;
        }
        .cnv1-engine-xray .xray-settings-primary > .xray-reality-save {
          width: 100%;
        }
      }
    `;
    document.head.append(style);
  };

  const bindRealityCopyActions = (container) => {
    container.querySelectorAll('.xray-copy-icon[data-copy-field]').forEach((button) => {
      button.addEventListener('click', async () => {
        const field = document.getElementById(button.dataset.copyField);
        if (!field) return;

        const original = button.textContent;
        try {
          await navigator.clipboard.writeText(field.value);
          button.textContent = '✓';
        } catch (_error) {
          field.focus();
          field.select();
          document.execCommand('copy');
          button.textContent = '✓';
        }
        window.setTimeout(() => {
          button.textContent = original;
        }, 1400);
      });
    });
  };

  const configureTwoRowXraySettings = () => {
    const fingerprintRow = document.querySelector('[data-fingerprint-panel]');
    const form = document.querySelector(
      '.cnv1-engine-xray form[action$="/connections/xray"]'
    );
    if (!fingerprintRow || !form) return;

    const details = form.closest('details');
    const grid = form.querySelector('.cnv1-form-grid');
    const parameterList = fingerprintRow.parentElement;
    if (!details || !grid || !parameterList) return;

    ensureXrayTwoRowStyles();

    form.id = 'xray-reality-form';
    form.classList.add('xray-reality-form-anchor');
    details.before(form);

    grid.querySelector('input[name="host"]')?.closest('label')?.remove();
    grid.querySelector('input[name="port"]')?.closest('label')?.remove();

    const serverName = grid.querySelector('input[name="server_name"]');
    const serverNameLabel = serverName?.closest('label');
    const submitButton = form.querySelector('button[type="submit"]');
    if (!serverName || !serverNameLabel || !submitButton) return;

    fingerprintRow.classList.add('xray-settings-primary');
    fingerprintRow.querySelector('.xps2-parameter-title')?.remove();
    const fingerprintCaption = fingerprintRow.querySelector('.xps2-field-mode > span');
    if (fingerprintCaption) fingerprintCaption.textContent = 'Client Fingerprint';

    serverNameLabel.classList.add('xray-reality-sni');
    serverName.setAttribute('form', form.id);
    submitButton.classList.add('xray-reality-save');
    submitButton.textContent = 'Сохранить SNI';
    submitButton.setAttribute('form', form.id);
    fingerprintRow.append(serverNameLabel, submitButton);

    const identityRow = document.createElement('article');
    identityRow.className = 'xps2-parameter-row is-visible xray-settings-identity';

    const prepareIdentityField = (field, id, labelText) => {
      if (!field) return null;
      field.id = id;
      field.readOnly = true;
      field.removeAttribute('name');
      field.setAttribute('aria-readonly', 'true');
      field.dataset.serverManaged = '1';
      field.title = 'Значение управляется сервером';
      if (field.tagName === 'TEXTAREA') field.rows = 1;

      const label = field.closest('label');
      if (!label) return null;
      label.classList.add('xray-reality-readonly');
      label.querySelector('[data-server-managed-note]')?.remove();
      const caption = label.querySelector(':scope > span');
      if (caption) caption.textContent = labelText;

      const valueRow = document.createElement('div');
      valueRow.className = 'xray-reality-value-row';
      field.replaceWith(valueRow);
      valueRow.append(field);

      const copyButton = document.createElement('button');
      copyButton.type = 'button';
      copyButton.className = 'button xray-copy-icon';
      copyButton.dataset.copyField = id;
      copyButton.textContent = '⧉';
      copyButton.title = `Копировать ${labelText}`;
      copyButton.setAttribute('aria-label', `Копировать ${labelText}`);
      valueRow.append(copyButton);
      return label;
    };

    const publicLabel = prepareIdentityField(
      grid.querySelector('textarea[name="public_key"]'),
      'xray-reality-public-key',
      'Reality public key'
    );
    const shortLabel = prepareIdentityField(
      grid.querySelector('input[name="short_id"]'),
      'xray-reality-short-id',
      'Short ID'
    );
    if (publicLabel) identityRow.append(publicLabel);
    if (shortLabel) identityRow.append(shortLabel);
    fingerprintRow.after(identityRow);

    form.querySelector('.cnv1-form-actions')?.remove();
    grid.remove();
    details.remove();
    bindRealityCopyActions(identityRow);
  };

  const ready = () => {
    configureFingerprintMenu();
    configureTwoRowXraySettings();

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
