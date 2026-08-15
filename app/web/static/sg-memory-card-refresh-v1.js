(() => {
  "use strict";
  let busy = false;
  async function refreshMemory() {
    if (busy || document.hidden) return;
    const current = document.querySelector('[data-sg-memory-card="1"]');
    if (!current) return;
    const button = current.querySelector('[data-sg-memory-refresh]');
    busy = true;
    if (button) button.disabled = true;
    try {
      const response = await fetch(window.location.href, {cache:"no-store", credentials:"same-origin", headers:{"X-SG-Partial":"memory"}});
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const html = await response.text();
      const doc = new DOMParser().parseFromString(html, "text/html");
      const next = doc.querySelector('[data-sg-memory-card="1"]');
      if (!next) throw new Error("memory card missing in response");
      current.replaceWith(next);
    } catch (err) {
      console.warn("SG-Gateway memory refresh:", err);
      if (button) button.disabled = false;
    } finally {
      busy = false;
    }
  }
  document.addEventListener("click", (e) => {
    const b=e.target.closest?.('[data-sg-memory-refresh]');
    if (!b) return;
    e.preventDefault(); refreshMemory();
  });
  window.setInterval(refreshMemory, 15000);
})();
