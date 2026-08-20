(() => {
  "use strict";
  const CARD_SELECTOR = '[data-sg-disk-card="1"]';
  const BUTTON_SELECTOR = '[data-sg-disk-refresh]';
  const STATUS_SELECTOR = '[data-sg-disk-refresh-status]';
  const CLEANUP_FORM_SELECTOR = '[data-sg-disk-cleanup-form]';
  const CLEANUP_STYLE_SELECTOR = '[data-sg-disk-cleanup-style]';
  let busy = false;

  function currentCard() {
    return document.querySelector(CARD_SELECTOR);
  }

  function setStatus(text) {
    const card = currentCard();
    const status = card && card.querySelector(STATUS_SELECTOR);
    if (status) status.textContent = text;
  }

  function ensureCleanupStyles() {
    if (document.querySelector(CLEANUP_STYLE_SELECTOR)) return;
    const link = document.createElement("link");
    link.rel = "stylesheet";
    link.href = "/static/sg-disk-cleanup-v1.css";
    link.dataset.sgDiskCleanupStyle = "1";
    document.head.appendChild(link);
  }

  function ensureCleanupButton() {
    ensureCleanupStyles();
    const card = currentCard();
    const slot = card && card.querySelector(".sg-resource-refresh-slot");
    if (!slot || slot.querySelector(CLEANUP_FORM_SELECTOR)) return;

    const form = document.createElement("form");
    form.method = "post";
    form.action = "/system/disk/cleanup";
    form.dataset.sgDiskCleanupForm = "1";

    const button = document.createElement("button");
    button.type = "submit";
    button.className = "button sv1-disk-cleanup";
    button.dataset.sgDiskCleanup = "1";
    button.innerHTML = '<span aria-hidden="true">⌫</span> Очистить';
    form.appendChild(button);

    form.addEventListener("submit", (event) => {
      const confirmed = window.confirm(
        "Очистить безопасный системный мусор? Бэкапы, база SG-Gateway, GeoFiles, клиенты и конфигурации удаляться не будут."
      );
      if (!confirmed) {
        event.preventDefault();
        return;
      }
      button.disabled = true;
      button.classList.add("is-loading");
      button.lastChild.textContent = " Запускаю…";
    });

    slot.appendChild(form);
  }

  async function refreshDisk(manual = false) {
    if (busy || document.hidden) return;
    const card = currentCard();
    if (!card) return;

    const button = card.querySelector(BUTTON_SELECTOR);
    busy = true;
    if (button) {
      button.disabled = true;
      button.classList.add("is-loading");
    }
    if (manual) setStatus("Обновляю…");

    try {
      const url = new URL(window.location.href);
      url.searchParams.set("disk_refresh", "1");
      url.searchParams.set("_", String(Date.now()));

      const response = await fetch(url.toString(), {
        method: "GET",
        headers: {"X-Requested-With": "SG-Disk-Refresh"},
        cache: "no-store",
        credentials: "same-origin",
      });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);

      const html = await response.text();
      const doc = new DOMParser().parseFromString(html, "text/html");
      const fresh = doc.querySelector(CARD_SELECTOR);
      const live = currentCard();
      if (!fresh || !live) throw new Error("disk card not found");

      live.innerHTML = fresh.innerHTML;
      ensureCleanupButton();
      setStatus(manual ? "Обновлено только что" : "Автообновление: 60 сек");
    } catch (_) {
      setStatus("Не удалось обновить");
    } finally {
      const active = currentCard();
      const activeButton = active && active.querySelector(BUTTON_SELECTOR);
      if (activeButton) {
        activeButton.disabled = false;
        activeButton.classList.remove("is-loading");
      }
      busy = false;
    }
  }

  document.addEventListener("click", (event) => {
    const button = event.target.closest(BUTTON_SELECTOR);
    if (!button) return;
    event.preventDefault();
    refreshDisk(true);
  });

  ensureCleanupButton();
  window.setInterval(() => refreshDisk(false), 60000);
})();
