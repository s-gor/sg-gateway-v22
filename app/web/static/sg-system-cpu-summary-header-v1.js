(() => {
  "use strict";

  function moveSummaryToHeader() {
    const heading = document.querySelector(".sv1-heading");
    const actions = heading?.querySelector(".sv1-heading-actions");
    const summary = document.querySelector(".sv1-cpu-summary");

    if (!heading || !actions || !summary) return;

    if (!summary.classList.contains("sg-cpu-summary-heading")) {
      summary.classList.add("sg-cpu-summary-heading");
    }

    if (summary.parentElement !== heading) {
      heading.insertBefore(summary, actions);
    }
  }

  let scheduled = false;
  function schedule() {
    if (scheduled) return;
    scheduled = true;
    requestAnimationFrame(() => {
      scheduled = false;
      moveSummaryToHeader();
    });
  }

  document.addEventListener("DOMContentLoaded", moveSummaryToHeader);

  new MutationObserver(schedule).observe(document.documentElement, {
    childList: true,
    subtree: true,
  });
})();
