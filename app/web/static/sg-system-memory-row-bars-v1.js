(() => {
  "use strict";

  function parsePercent(text) {
    const raw = String(text || '').replace(',', '.');
    const match = raw.match(/(-?\d+(?:\.\d+)?)\s*%/);
    if (!match) return 0;
    const value = Number(match[1]);
    if (!Number.isFinite(value)) return 0;
    return Math.max(0, Math.min(100, value));
  }

  function ensureMemoryBars() {
    const rows = document.querySelectorAll('.sv1-memory-legend .sv1-legend-row');
    rows.forEach((row) => {
      const percentNode = row.querySelector('em');
      if (!percentNode) return;

      const width = parsePercent(percentNode.textContent);
      const dot = row.querySelector('.sv1-legend-dot');
      const color = dot ? getComputedStyle(dot).backgroundColor || getComputedStyle(dot).getPropertyValue('--legend-color').trim() : '';

      let track = row.querySelector(':scope > .sg-memory-row-track');
      if (!track) {
        track = document.createElement('div');
        track.className = 'sg-memory-row-track';
        const fill = document.createElement('span');
        track.appendChild(fill);
        row.appendChild(track);
      }

      row.classList.add('sg-mem-row-with-track');
      if (color) row.style.setProperty('--sg-memory-row-color', color);
      const fill = track.firstElementChild;
      if (fill) fill.style.width = width + '%';
    });
  }

  let scheduled = false;
  function schedule() {
    if (scheduled) return;
    scheduled = true;
    requestAnimationFrame(() => {
      scheduled = false;
      ensureMemoryBars();
    });
  }

  document.addEventListener('DOMContentLoaded', ensureMemoryBars);
  new MutationObserver(schedule).observe(document.documentElement, {
    childList: true,
    subtree: true,
    characterData: true,
  });
})();
