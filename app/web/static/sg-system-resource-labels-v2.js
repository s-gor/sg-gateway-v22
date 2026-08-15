(() => {
  "use strict";

  const trim = (value) => String(value || "").replace(/\s+/g, " ").trim();

  function parsePercent(text) {
    const match = String(text || "").match(/(-?\d+(?:[.,]\d+)?)\s*%/);
    if (!match) return null;
    const value = Number(match[1].replace(",", "."));
    if (!Number.isFinite(value)) return null;
    return Math.max(0, Math.min(100, Math.round(value)));
  }

  function textAfterColon(node) {
    if (!node) return "";
    const strong = node.querySelector("strong");
    if (strong) return trim(strong.textContent);
    const text = trim(node.textContent);
    const pos = text.indexOf(":");
    return pos >= 0 ? trim(text.slice(pos + 1)) : text;
  }

  function findInfoLine(copy, pattern) {
    return [...copy.querySelectorAll(".sv1-resource-available")]
      .find((node) => pattern.test(trim(node.textContent)));
  }

  function ensureTotalLine(copy, occupiedLine, totalValue) {
    let totalLine = copy.querySelector(".sg-resource-total-line");
    if (!totalLine) {
      totalLine = document.createElement("div");
      totalLine.className = "sv1-resource-available sg-resource-total-line";
      occupiedLine.insertAdjacentElement("afterend", totalLine);
    }
    totalLine.innerHTML = `Всего: <strong>${totalValue}</strong>`;
  }

  function ensureBarLabels(wrapper, availablePercent, occupiedPercent) {
    if (!wrapper) return;
    let spans = [...wrapper.querySelectorAll(":scope > span")];
    while (spans.length < 2) {
      const span = document.createElement("span");
      wrapper.appendChild(span);
      spans = [...wrapper.querySelectorAll(":scope > span")];
    }
    spans[0].textContent = `Доступно ${availablePercent}%`;
    spans[1].textContent = `Занято ${occupiedPercent}%`;
  }

  function applyCard({
    selector,
    progressSelector,
    labelsSelector,
    freePattern,
  }) {
    const card = document.querySelector(selector);
    if (!card) return;

    const centerStrong = card.querySelector(".sv1-donut-center strong");
    const centerLabel = card.querySelector(".sv1-donut-center span");
    const copy = card.querySelector(".sv1-resource-copy");
    const number = copy?.querySelector(".sv1-resource-number");
    const subtitle = copy?.querySelector(".sv1-resource-total");

    if (!centerStrong || !centerLabel || !copy || !number || !subtitle) return;

    if (
      trim(centerLabel.textContent) === "Доступно"
      && trim(subtitle.textContent) === "Доступно"
      && copy.querySelector(".sg-resource-total-line")
    ) {
      return;
    }

    const occupiedPercent = parsePercent(centerStrong.textContent);
    if (occupiedPercent === null) return;

    const availablePercent = Math.max(0, 100 - occupiedPercent);
    const occupiedValue = trim(number.textContent);
    const totalValue = trim(subtitle.textContent).replace(/^из\s+/i, "");

    const availableLine = findInfoLine(copy, freePattern);
    if (!availableLine) return;
    const availableValue = textAfterColon(availableLine);
    if (!availableValue || !totalValue || !occupiedValue) return;

    centerStrong.textContent = `${availablePercent}%`;
    centerLabel.textContent = "Доступно";

    number.textContent = availableValue;
    subtitle.textContent = "Доступно";

    availableLine.innerHTML = `Занято: <strong>${occupiedValue}</strong>`;
    ensureTotalLine(copy, availableLine, totalValue);

    const progress = card.querySelector(progressSelector);
    if (progress) {
      progress.style.width = `${availablePercent}%`;
    }

    ensureBarLabels(
      card.querySelector(labelsSelector),
      availablePercent,
      occupiedPercent
    );
  }

  function ensureDiskLogPath() {
    const card = document.querySelector('[data-sg-disk-card="1"]');
    const copy = card?.querySelector(".sv1-resource-copy");
    if (!copy) return;

    const lines = [...copy.querySelectorAll(".sv1-resource-available")];
    const line = lines.find((node) =>
      /файловая\s+система|логи/i.test(trim(node.textContent))
    );
    if (!line) return;

    if (
      line.dataset.sgDiskLogPath === "1"
      && trim(line.textContent) === "Логи: /var/log/sg-gateway"
    ) {
      return;
    }

    line.innerHTML = 'Логи: <strong>/var/log/sg-gateway</strong>';
    line.dataset.sgDiskLogPath = "1";
  }

  function applyAll() {
    applyCard({
      selector: '[data-sg-memory-card="1"]',
      progressSelector: ".sv1-peer-progress-memory .sv1-peer-progress-track > span",
      labelsSelector: ".sv1-peer-progress-memory .sv1-peer-progress-labels",
      freePattern: /доступно|свободно/i,
    });

    applyCard({
      selector: '[data-sg-disk-card="1"]',
      progressSelector: ".sv1-disk-bar > span",
      labelsSelector: ".sv1-disk-labels",
      freePattern: /свободно|доступно/i,
    });

    ensureDiskLogPath();
  }

  let scheduled = false;
  function scheduleApply() {
    if (scheduled) return;
    scheduled = true;
    window.requestAnimationFrame(() => {
      scheduled = false;
      applyAll();
    });
  }

  document.addEventListener("DOMContentLoaded", applyAll);

  const observer = new MutationObserver(scheduleApply);
  observer.observe(document.documentElement, {
    childList: true,
    subtree: true,
  });
})();
