(() => {
  "use strict";

  const SQLITE_UPLOAD_ACTION = "/maintenance/backups/__upload__/restore";
  const MAINTENANCE_UI_REVISION = "clients-keys-https-sqlite-v2";

  function filenameFromResponse(response, href) {
    const disposition = response.headers.get("Content-Disposition") || "";
    const utf8 = disposition.match(/filename\*=UTF-8''([^;]+)/i);
    if (utf8) {
      try {
        return decodeURIComponent(utf8[1].trim());
      } catch (_) {}
    }
    const plain = disposition.match(/filename="?([^";]+)"?/i);
    if (plain && plain[1]) return plain[1].trim();
    try {
      const part = new URL(href, window.location.href).pathname.split("/").filter(Boolean).pop();
      return part ? decodeURIComponent(part) : "SG-Gateway-CLIENTS.sgbackup";
    } catch (_) {
      return "SG-Gateway-CLIENTS.sgbackup";
    }
  }

  function installClientsKeysDownload() {
    const anchor = document.querySelector(".sg-data-backup-card .sg-full-download");
    if (!(anchor instanceof HTMLAnchorElement) || anchor.dataset.sgClientsKeysDownload === "1") return;
    anchor.dataset.sgClientsKeysDownload = "1";

    anchor.addEventListener("click", async (event) => {
      event.preventDefault();
      if (anchor.getAttribute("aria-busy") === "true") return;

      const label = anchor.querySelector("span");
      const originalLabel = label ? label.textContent : "";
      anchor.setAttribute("aria-busy", "true");
      anchor.classList.add("is-loading");
      if (label) label.textContent = "Скачивание…";

      try {
        const response = await fetch(anchor.href, {
          method: "GET",
          credentials: "same-origin",
          cache: "no-store",
          redirect: "follow",
          headers: { Accept: "application/octet-stream, application/gzip, */*" },
        });
        if (!response.ok) {
          throw new Error(`HTTP ${response.status}`);
        }
        const disposition = response.headers.get("Content-Disposition") || "";
        if (!/attachment/i.test(disposition)) {
          throw new Error("server response is not an attachment");
        }

        const blob = await response.blob();
        if (!blob.size) throw new Error("downloaded backup is empty");

        const objectUrl = URL.createObjectURL(blob);
        const download = document.createElement("a");
        download.href = objectUrl;
        download.download = filenameFromResponse(response, anchor.href);
        download.hidden = true;
        document.body.appendChild(download);
        download.click();
        download.remove();
        window.setTimeout(() => URL.revokeObjectURL(objectUrl), 1000);
      } catch (error) {
        console.error("Clients, Keys & HTTPS download failed", error);
        window.location.assign(anchor.href);
      } finally {
        anchor.removeAttribute("aria-busy");
        anchor.classList.remove("is-loading");
        if (label && originalLabel) label.textContent = originalLabel;
      }
    });
  }

  function normalizeClientsKeysHttpsCopy() {
    const card = document.querySelector(".sg-data-backup-card");
    if (!card) return;

    card.dataset.sgClientsKeysHttpsUi = MAINTENANCE_UI_REVISION;

    const kicker = card.querySelector(".mtv2-card-kicker");
    const title = card.querySelector("h2");
    const intro = card.querySelector(".sg-full-backup-head p");
    const createButton = card.querySelector(".sg-full-backup-head form button span");
    if (kicker) kicker.textContent = "CLIENTS, KEYS & HTTPS";
    if (title) title.textContent = "Клиенты, ключи и HTTPS";
    if (intro) {
      intro.textContent =
        "Переносимая копия клиентов, устройств, их ключей и активного HTTPS. Настройки сервера не переносятся.";
    }
    if (createButton) createButton.textContent = "Создать Clients, Keys & HTTPS";

    const sections = card.querySelectorAll(".sg-full-section-title");
    const contents = sections[0];
    if (contents) {
      const strong = contents.querySelector("strong");
      const small = contents.querySelector("small");
      if (strong) strong.textContent = "Что переносится";
      if (small) {
        small.textContent =
          "Клиентские данные, реквизиты доступа и активная HTTPS-идентичность.";
      }
    }

    const components = card.querySelector(".sg-full-backup-components");
    if (components) {
      components.innerHTML =
        "<em>Клиенты</em><em>Устройства</em><em>Ключи</em><em>UUID</em><em>Пароли</em><em>SG SUB</em><em>Router SUB</em><em>HTTPS</em><em>TLS cert</em>";
    }

    const detail = card.querySelector(".sg-full-backup-detail");
    if (detail) {
      detail.textContent =
        "Переносятся активный HTTPS-домен, сертификат и private key. Routing, WARP, настройки протоколов, адреса и серверный runtime не копируются.";
    }

    const warning = card.querySelector(".sg-full-backup-warning span");
    if (warning) {
      warning.innerHTML =
        "<strong>Без настроек сервера.</strong> После Restore нужные протоколы включаются на новом сервере вручную; сохранённые клиенты и их ключи используются повторно.";
    }

    const restoreSection = sections[1];
    if (restoreSection) {
      const strong = restoreSection.querySelector("strong");
      const small = restoreSection.querySelector("small");
      if (strong) strong.textContent = "Восстановить клиентов, ключи и HTTPS";
      if (small) {
        small.textContent =
          "Файл проверяется до изменения данных; настройки и состояние протоколов текущего сервера сохраняются.";
      }
    }

    const form = card.querySelector("[data-sg-full-upload]");
    if (form) {
      form.dataset.sgConfirm =
        "Восстановить клиентов, ключи и HTTPS из проверенного файла? Настройки и состояние протоколов текущего сервера останутся без изменений.";
      form.dataset.sgConfirmTitle = "Восстановить Clients, Keys & HTTPS";
      const pickerName = form.querySelector("[data-sg-full-file-name]");
      const note = form.querySelector(".sg-full-restore-note");
      const verifyText = form.querySelector("[data-sg-full-verify-button] span");
      const restoreText = form.querySelector("[data-sg-full-restore-button] span");
      if (pickerName) pickerName.textContent = "Выберите Clients, Keys & HTTPS .sgbackup";
      if (note) {
        note.textContent =
          "Restore возвращает клиентов, их реквизиты и активный HTTPS. Перед изменением создаётся страховочный Full Backup.";
      }
      if (verifyText) verifyText.textContent = "Проверить backup";
      if (restoreText) restoreText.textContent = "Восстановить";
    }

    const latest = card.querySelector(".sg-full-latest-label");
    const download = card.querySelector(".sg-full-download span");
    if (latest) latest.textContent = "ПОСЛЕДНИЙ CLIENTS, KEYS & HTTPS BACKUP";
    if (download) download.textContent = "Скачать Clients, Keys & HTTPS";
  }

  function installSqliteUploadRestore() {
    const panels = Array.from(document.querySelectorAll(".mtv2-backup-panel"));
    const panel = panels.find((item) => {
      const title = item.querySelector("h2");
      return title && String(title.textContent || "").includes("Последняя копия базы данных");
    });
    if (!panel || panel.querySelector("[data-sg-sqlite-upload]")) return;

    const actions = panel.querySelector(".mtv2-backup-head-actions");
    if (!actions) return;

    const form = document.createElement("form");
    form.method = "post";
    form.action = SQLITE_UPLOAD_ACTION;
    form.enctype = "multipart/form-data";
    form.dataset.sgSqliteUpload = "1";
    form.dataset.sgConfirm =
      "Восстановить базу из выбранного .sqlite? Сначала файл будет проверен. Перед заменой текущей базы автоматически создастся pre-restore копия; при ошибке runtime будет выполнен возврат.";
    form.dataset.sgConfirmTitle = "Восстановить базу из файла";
    form.dataset.sgConfirmButton = "Проверить и восстановить";
    form.dataset.sgConfirmTone = "danger";

    const picker = document.createElement("label");
    picker.className = "button";
    picker.title = "Выбрать скачанную SQLite-копию SG-Gateway";
    const pickerText = document.createElement("span");
    pickerText.textContent = "Выбрать .sqlite";
    const input = document.createElement("input");
    input.type = "file";
    input.name = "backup";
    input.accept = ".sqlite,application/x-sqlite3,application/vnd.sqlite3";
    input.required = true;
    input.hidden = true;
    picker.append(pickerText, input);

    const submit = document.createElement("button");
    submit.className = "button";
    submit.type = "submit";
    submit.disabled = true;
    submit.textContent = "Восстановить из файла";

    input.addEventListener("change", () => {
      const file = input.files && input.files[0];
      submit.disabled = !file;
      pickerText.textContent = file ? file.name : "Выбрать .sqlite";
      picker.title = file ? `Выбрано: ${file.name}` : "Выбрать скачанную SQLite-копию SG-Gateway";
    });

    form.append(picker, submit);
    actions.prepend(form);
  }

  normalizeClientsKeysHttpsCopy();
  installClientsKeysDownload();
  installSqliteUploadRestore();
})();
