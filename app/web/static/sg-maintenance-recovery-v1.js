(() => {
  "use strict";

  const FULL_RESTORE_PATH = "/maintenance/full-backups/restore";
  const AUTO_RESTORE_KEY = "sg-full-restore-after-verify-v1";

  function fullRestoreForm() {
    return Array.from(document.querySelectorAll("[data-sg-full-upload]")).find((form) => {
      try {
        return new URL(form.action, window.location.href).pathname === FULL_RESTORE_PATH;
      } catch (_) {
        return false;
      }
    }) || null;
  }

  function enhanceFullRestore() {
    const form = fullRestoreForm();
    if (!form) return;

    const input = form.querySelector("[data-sg-full-file]");
    const oldVerifyButton = form.querySelector("[data-sg-full-verify-button]");
    const restoreButton = form.querySelector("[data-sg-full-restore-button]");
    const note = form.querySelector(".sg-full-restore-note");
    if (!input || !oldVerifyButton || !restoreButton) return;

    form.dataset.sgConfirm = "Проверить выбранный .sgbackup и, если файл исправен, сразу начать полное восстановление? Перед изменением текущего сервера будет автоматически создан страховочный Full Backup.";
    form.dataset.sgConfirmTitle = "Проверка и восстановление SG-Gateway";
    form.dataset.sgConfirmButton = "Проверить и восстановить";
    form.dataset.sgConfirmTone = "danger";

    if (note) {
      note.textContent = "Сначала SG-Gateway полностью проверит файл. Если проверка успешна, восстановление начнётся автоматически. Перед изменением создаётся страховочный Full Backup.";
    }

    oldVerifyButton.hidden = true;
    oldVerifyButton.setAttribute("aria-hidden", "true");
    oldVerifyButton.tabIndex = -1;

    restoreButton.hidden = true;
    restoreButton.setAttribute("aria-hidden", "true");
    restoreButton.tabIndex = -1;
    restoreButton.style.display = "none";

    const actionButton = document.createElement("button");
    actionButton.type = "submit";
    actionButton.name = "backup_action";
    actionButton.value = "verify";
    actionButton.className = oldVerifyButton.className;
    actionButton.dataset.sgFullAutoRestore = "1";
    actionButton.disabled = !(input.files && input.files[0]);
    actionButton.innerHTML = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="m5 12 4 4L19 6"/></svg><span>Проверить и восстановить</span>';
    oldVerifyButton.insertAdjacentElement("beforebegin", actionButton);

    input.addEventListener("change", () => {
      actionButton.disabled = !(input.files && input.files[0]);
    });

    form.addEventListener("submit", (event) => {
      if (event.defaultPrevented || event.submitter !== actionButton) return;
      const file = input.files && input.files[0];
      if (!file) return;
      try {
        window.sessionStorage.setItem(AUTO_RESTORE_KEY, file.name);
      } catch (_) {}
    });

    let pendingName = "";
    try {
      pendingName = window.sessionStorage.getItem(AUTO_RESTORE_KEY) || "";
    } catch (_) {}

    const hasVerifiedBackup = form.dataset.sgFullVerified === "1";
    const verifiedName = form.dataset.sgVerifiedName || "";
    if (pendingName && !hasVerifiedBackup) {
      try { window.sessionStorage.removeItem(AUTO_RESTORE_KEY); } catch (_) {}
      return;
    }

    if (!pendingName || !hasVerifiedBackup || pendingName !== verifiedName) return;

    try { window.sessionStorage.removeItem(AUTO_RESTORE_KEY); } catch (_) {}
    restoreButton.disabled = false;
    window.setTimeout(() => {
      form.dataset.sgConfirmBypass = "1";
      if (typeof form.requestSubmit === "function") {
        form.requestSubmit(restoreButton);
      } else {
        restoreButton.click();
      }
    }, 80);
  }

  function addDiskCleanupCard() {
    if (!fullRestoreForm() || document.querySelector("[data-sg-maintenance-disk-cleanup]")) return;
    const mainGrid = document.querySelector(".mtv2-main-grid");
    if (!mainGrid) return;

    const card = document.createElement("article");
    card.className = "mtv2-panel sg-ljd-card-large";
    card.dataset.sgMaintenanceDiskCleanup = "1";
    card.innerHTML = `
      <header class="mtv2-panel-head">
        <div>
          <div class="mtv2-card-kicker">ОБСЛУЖИВАНИЕ ДИСКА</div>
          <h2>Безопасная очистка диска</h2>
          <p>Удаляет только системный кэш, старый journal, временные файлы по системным правилам и устаревшие журналы фоновых задач SG-Gateway.</p>
        </div>
        <form method="post" action="/system/disk/cleanup"
              data-sg-confirm="Очистить безопасный системный мусор? Резервные копии, база SG-Gateway, GeoFiles, клиенты, ключи и конфигурации удаляться не будут."
              data-sg-confirm-title="Безопасная очистка диска"
              data-sg-confirm-button="Очистить"
              data-sg-confirm-tone="warning">
          <button class="button primary" type="submit">Очистить диск</button>
        </form>
      </header>
      <div class="mtv31-safety-note sg-ljd-nested">
        <strong>Данные SG-Gateway не затрагиваются</strong>
        <span>Full Backup, DATA Backup, SQLite, GeoFiles, клиенты, ключи и рабочие конфигурации остаются без изменений.</span>
      </div>`;
    mainGrid.insertAdjacentElement("afterend", card);
  }

  function operationSecureUrl(root) {
    const log = document.getElementById("opjob-log");
    const restoreAddress = String(log?.textContent || "").match(
      /\[Restore 6\/7\] Адрес панели после переключения: (https:\/\/[^\s]+)/
    );
    const secure = restoreAddress ? new URL(restoreAddress[1]) : new URL(window.location.href);
    secure.protocol = "https:";
    secure.pathname = window.location.pathname;
    secure.search = window.location.search;
    secure.hash = window.location.hash;
    return secure;
  }

  function enhanceOperationRestartReconnect() {
    const root = document.querySelector('.opjob-page[data-restart-expected="1"]');
    if (!root || window.location.protocol !== "http:") return;

    let redirecting = false;
    let stopped = false;

    const probe = async () => {
      if (redirecting || stopped) return;
      const badge = document.getElementById("opjob-status");
      const status = String(badge?.textContent || "").trim();
      if (status === "success" || status === "failed") {
        stopped = true;
        return;
      }

      let secureJobUrl;
      try {
        secureJobUrl = operationSecureUrl(root);
      } catch (_) {
        window.setTimeout(probe, 1800);
        return;
      }
      const secureStatusUrl = new URL(root.dataset.statusUrl || window.location.pathname, secureJobUrl);
      secureStatusUrl.protocol = "https:";
      secureStatusUrl.hostname = secureJobUrl.hostname;
      secureStatusUrl.port = secureJobUrl.port;

      try {
        await fetch(secureStatusUrl.toString(), {
          mode: "no-cors",
          cache: "no-store",
          credentials: "omit",
        });
      } catch (_) {
        window.setTimeout(probe, 1800);
        return;
      }

      redirecting = true;
      const message = document.getElementById("opjob-message");
      if (message) {
        message.textContent = "Панель снова доступна по HTTPS. Переподключаю этот же терминал автоматически…";
      }
      window.setTimeout(() => window.location.replace(secureJobUrl.toString()), 350);
    };

    window.setTimeout(probe, 2500);
  }

  enhanceFullRestore();
  addDiskCleanupCard();
  enhanceOperationRestartReconnect();
})();