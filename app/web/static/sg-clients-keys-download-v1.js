(() => {
  "use strict";

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
        console.error("Clients & Keys download failed", error);
        window.location.assign(anchor.href);
      } finally {
        anchor.removeAttribute("aria-busy");
        anchor.classList.remove("is-loading");
        if (label && originalLabel) label.textContent = originalLabel;
      }
    });
  }

  installClientsKeysDownload();
})();
