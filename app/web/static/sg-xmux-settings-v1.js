(() => {
  const configureFingerprintMenu = () => {
    const fingerprint = document.querySelector(
      '[data-fingerprint-panel] select[name="fingerprint"]'
    );
    if (!fingerprint || fingerprint.dataset.sgPickerReady === '1') return;

    const field = fingerprint.closest('.xps2-field-mode');
    if (!field) return;

    fingerprint.dataset.sgPickerReady = '1';

    const selectStyles = getComputedStyle(fingerprint);
    const picker = document.createElement('div');
    picker.className = 'xray-fingerprint-picker';
    picker.style.setProperty('--xray-picker-bg', selectStyles.backgroundColor);
    picker.style.setProperty('--xray-picker-color', selectStyles.color);
    picker.style.setProperty('--xray-picker-border', selectStyles.borderColor);
    picker.style.setProperty('--xray-picker-radius', selectStyles.borderRadius);

    const trigger = document.createElement('button');
    trigger.type = 'button';
    trigger.className = 'xray-fingerprint-trigger';
    trigger.setAttribute('aria-haspopup', 'listbox');
    trigger.setAttribute('aria-expanded', 'false');

    const triggerText = document.createElement('span');
    triggerText.className = 'xray-fingerprint-trigger-text';
    const triggerArrow = document.createElement('span');
    triggerArrow.className = 'xray-fingerprint-trigger-arrow';
    triggerArrow.setAttribute('aria-hidden', 'true');
    triggerArrow.textContent = '⌄';
    trigger.append(triggerText, triggerArrow);

    const menu = document.createElement('div');
    menu.id = 'xray-fingerprint-menu';
    menu.className = 'xray-fingerprint-menu';
    menu.setAttribute('role', 'listbox');
    menu.hidden = true;
    trigger.setAttribute('aria-controls', menu.id);

    const optionButtons = [];
    const addOption = (option) => {
      const optionButton = document.createElement('button');
      optionButton.type = 'button';
      optionButton.className = 'xray-fingerprint-option';
      optionButton.dataset.value = option.value;
      optionButton.textContent = option.textContent.trim();
      optionButton.setAttribute('role', 'option');
      optionButton.disabled = option.disabled;
      menu.append(optionButton);
      optionButtons.push(optionButton);

      optionButton.addEventListener('click', () => {
        fingerprint.value = optionButton.dataset.value;
        fingerprint.dispatchEvent(new Event('input', { bubbles: true }));
        fingerprint.dispatchEvent(new Event('change', { bubbles: true }));
        closeMenu(true);
      });
    };

    [...fingerprint.children].forEach((item) => {
      if (item.tagName === 'OPTGROUP') {
        const groupLabel = document.createElement('div');
        groupLabel.className = 'xray-fingerprint-group';
        groupLabel.textContent = item.label;
        menu.append(groupLabel);
        [...item.children].forEach(addOption);
      } else if (item.tagName === 'OPTION') {
        addOption(item);
      }
    });

    const syncSelection = () => {
      triggerText.textContent = fingerprint.selectedOptions[0]?.textContent.trim() || '';
      optionButtons.forEach((optionButton) => {
        const selected = optionButton.dataset.value === fingerprint.value;
        optionButton.classList.toggle('is-selected', selected);
        optionButton.setAttribute('aria-selected', String(selected));
      });
    };

    const focusSelected = () => {
      const selected = optionButtons.find(
        (optionButton) => optionButton.dataset.value === fingerprint.value
      );
      (selected || optionButtons.find((optionButton) => !optionButton.disabled))?.focus();
    };

    const positionMenu = () => {
      const rect = trigger.getBoundingClientRect();
      const viewportGap = 12;
      const preferredHeight = 340;
      const spaceBelow = window.innerHeight - rect.bottom - viewportGap;
      const spaceAbove = rect.top - viewportGap;
      const openUp = spaceBelow < preferredHeight && spaceAbove > spaceBelow;
      const availableSpace = openUp ? spaceAbove : spaceBelow;
      const availableHeight = Math.max(96, Math.min(preferredHeight, availableSpace));
      menu.classList.toggle('opens-up', openUp);
      menu.style.maxHeight = `${availableHeight}px`;
    };

    const repositionOpenMenu = () => {
      if (!menu.hidden) positionMenu();
    };

    const openMenu = () => {
      menu.hidden = false;
      positionMenu();
      picker.classList.add('is-open');
      trigger.setAttribute('aria-expanded', 'true');
      window.requestAnimationFrame(focusSelected);
    };

    function closeMenu(returnFocus = false) {
      menu.hidden = true;
      menu.classList.remove('opens-up');
      menu.style.removeProperty('max-height');
      picker.classList.remove('is-open');
      trigger.setAttribute('aria-expanded', 'false');
      if (returnFocus) trigger.focus();
    }

    trigger.addEventListener('click', () => {
      if (menu.hidden) openMenu();
      else closeMenu();
    });
    trigger.addEventListener('keydown', (event) => {
      if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
        event.preventDefault();
        openMenu();
      }
    });
    menu.addEventListener('keydown', (event) => {
      const enabledOptions = optionButtons.filter((optionButton) => !optionButton.disabled);
      const currentIndex = enabledOptions.indexOf(document.activeElement);
      if (event.key === 'Escape') {
        event.preventDefault();
        closeMenu(true);
        return;
      }
      if (!['ArrowDown', 'ArrowUp', 'Home', 'End'].includes(event.key)) return;
      event.preventDefault();
      let nextIndex = currentIndex;
      if (event.key === 'Home') nextIndex = 0;
      else if (event.key === 'End') nextIndex = enabledOptions.length - 1;
      else if (event.key === 'ArrowDown') nextIndex = (currentIndex + 1) % enabledOptions.length;
      else nextIndex = (currentIndex - 1 + enabledOptions.length) % enabledOptions.length;
      enabledOptions[nextIndex]?.focus();
    });
    document.addEventListener('click', (event) => {
      if (!picker.contains(event.target)) closeMenu();
    });
    window.addEventListener('resize', repositionOpenMenu);
    window.addEventListener('scroll', repositionOpenMenu, true);
    fingerprint.addEventListener('change', syncSelection);

    fingerprint.hidden = true;
    field.append(picker);
    picker.append(trigger, menu);
    syncSelection();
  };

  const ensureXrayTwoRowStyles = () => {
    if (document.getElementById('xray-two-row-styles')) return;

    const style = document.createElement('style');
    style.id = 'xray-two-row-styles';
    style.textContent = `
      .cnv1-engine-xray .xray-settings-primary {
        display: grid !important;
        grid-template-columns: repeat(2, minmax(0, 1fr)) !important;
        grid-template-areas: "fingerprint sni" !important;
        align-items: end;
        gap: 10px 14px;
        overflow: visible;
        padding: 12px 14px;
      }
      .cnv1-engine-xray .xray-settings-primary .xps2-parameter-title {
        display: none !important;
      }
      .cnv1-engine-xray .xray-settings-primary > .xps2-field-mode {
        grid-area: fingerprint !important;
        min-width: 0;
      }
      .cnv1-engine-xray .xray-reality-sni-group {
        display: grid;
        grid-area: sni;
        grid-template-columns: minmax(0, 1fr) auto;
        align-items: end;
        min-width: 0;
        gap: 12px;
      }
      .cnv1-engine-xray .xray-reality-sni-group > .xray-reality-sni {
        display: grid;
        width: 100% !important;
        max-width: none !important;
        min-width: 0;
        gap: 5px;
      }
      .cnv1-engine-xray .xray-reality-sni-group > .xray-reality-sni input {
        width: 100% !important;
        max-width: none !important;
        min-width: 0;
      }
      .cnv1-engine-xray .xray-settings-primary label > span {
        display: block !important;
        color: var(--sg-muted);
        font-size: 9.5px;
        font-weight: 800;
        letter-spacing: .025em;
      }
      .cnv1-engine-xray .xray-settings-primary .xps2-field-mode > small {
        display: none !important;
      }
      .cnv1-engine-xray .xray-settings-primary input {
        width: 100%;
        min-width: 0;
        min-height: 42px;
      }
      .cnv1-engine-xray .xray-reality-sni-group > .xray-reality-save {
        min-height: 42px;
        padding-inline: 16px;
        white-space: nowrap;
      }
      .cnv1-engine-xray .xray-fingerprint-picker {
        --xray-picker-menu-bg: #10253a;
        position: relative;
        width: 100%;
        min-width: 0;
      }
      .cnv1-engine-xray .xray-fingerprint-trigger {
        display: grid;
        grid-template-columns: minmax(0, 1fr) auto;
        align-items: center;
        width: 100%;
        min-height: 42px;
        border: 1px solid var(--xray-picker-border, var(--line));
        border-radius: var(--xray-picker-radius, 8px);
        background: var(--xray-picker-bg, var(--panel-3));
        color: var(--xray-picker-color, var(--text));
        padding: 0 13px;
        text-align: left;
        cursor: pointer;
      }
      .cnv1-engine-xray .xray-fingerprint-trigger:hover,
      .cnv1-engine-xray .xray-fingerprint-trigger:focus-visible,
      .cnv1-engine-xray .xray-fingerprint-picker.is-open .xray-fingerprint-trigger {
        border-color: var(--blue);
        outline: none;
        box-shadow: 0 0 0 2px rgba(98, 168, 255, .13);
      }
      .cnv1-engine-xray .xray-fingerprint-trigger-text {
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
      }
      .cnv1-engine-xray .xray-fingerprint-trigger-arrow {
        margin-left: 12px;
        color: var(--sg-muted, var(--muted));
        font-size: 17px;
        line-height: 1;
        transition: transform .16s ease;
      }
      .cnv1-engine-xray .xray-fingerprint-picker.is-open .xray-fingerprint-trigger-arrow {
        transform: rotate(180deg);
      }
      .cnv1-engine-xray .xray-fingerprint-menu {
        position: absolute;
        z-index: 500;
        top: calc(100% + 6px);
        right: 0;
        left: 0;
        overflow-y: auto;
        overscroll-behavior: contain;
        scrollbar-gutter: stable;
        isolation: isolate;
        opacity: 1;
        border: 1px solid var(--xray-picker-border, var(--line));
        border-radius: var(--xray-picker-radius, 8px);
        background: var(--xray-picker-menu-bg);
        color: var(--xray-picker-color, var(--text));
        padding: 6px;
        box-shadow: 0 20px 48px rgba(0, 0, 0, .58);
        backdrop-filter: none;
      }
      .cnv1-engine-xray .xray-fingerprint-menu.opens-up {
        top: auto;
        bottom: calc(100% + 6px);
      }
      html[data-theme="light"] .cnv1-engine-xray .xray-fingerprint-menu {
        background: #f8fafc;
        box-shadow: 0 18px 42px rgba(28, 45, 62, .24);
      }
      .cnv1-engine-xray .xray-fingerprint-menu[hidden] {
        display: none !important;
      }
      .cnv1-engine-xray .xray-fingerprint-group {
        padding: 9px 10px 5px;
        color: var(--sg-muted, var(--muted));
        font-size: 11px;
        font-weight: 800;
        letter-spacing: .045em;
        text-transform: uppercase;
      }
      .cnv1-engine-xray .xray-fingerprint-option {
        display: block;
        width: 100%;
        min-height: 36px;
        border: 1px solid transparent;
        border-radius: 7px;
        background: transparent;
        color: inherit;
        padding: 7px 10px;
        text-align: left;
        cursor: pointer;
      }
      .cnv1-engine-xray .xray-fingerprint-option:hover,
      .cnv1-engine-xray .xray-fingerprint-option:focus-visible {
        border-color: rgba(98, 168, 255, .34);
        background: rgba(98, 168, 255, .14);
        outline: none;
      }
      .cnv1-engine-xray .xray-fingerprint-option.is-selected {
        border-color: rgba(98, 168, 255, .58);
        background: rgba(98, 168, 255, .24);
        font-weight: 750;
      }
      .cnv1-engine-xray .xray-fingerprint-option:disabled {
        display: none;
      }
      .cnv1-engine-xray .xray-settings-identity {
        display: grid !important;
        grid-template-columns: repeat(2, minmax(0, 1fr)) !important;
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
        .cnv1-engine-xray .xray-settings-primary,
        .cnv1-engine-xray .xray-settings-identity {
          grid-template-columns: minmax(0, 1fr) !important;
        }
        .cnv1-engine-xray .xray-settings-primary {
          grid-template-areas:
            "fingerprint"
            "sni" !important;
        }
      }
      @media (max-width: 620px) {
        .cnv1-engine-xray .xray-reality-sni-group {
          grid-template-columns: minmax(0, 1fr);
        }
        .cnv1-engine-xray .xray-reality-sni-group > .xray-reality-save {
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
    const sniGroup = document.createElement('div');
    sniGroup.className = 'xray-reality-sni-group';
    sniGroup.append(serverNameLabel, submitButton);
    fingerprintRow.append(sniGroup);

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
        reduced: 'Для РФ — быстрая ротация',
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
