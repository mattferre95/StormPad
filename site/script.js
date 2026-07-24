const DOWNLOAD_URL =
  "https://github.com/mattferre95/StormPad/releases/latest/download/StormPad-0.1.0.dmg";

// Change to true only after the official DMG exists at DOWNLOAD_URL.
const DOWNLOAD_AVAILABLE = false;

const header = document.querySelector("[data-header]");
const modal = document.querySelector("[data-modal]");
const modalPanel = document.querySelector("[data-modal-panel]");
const downloadButtons = document.querySelectorAll(".js-download");
const closeButtons = document.querySelectorAll("[data-modal-close]");
const downloadStatus = document.querySelector("[data-download-status]");

let returnFocusTo = null;

function updateHeader() {
  header.classList.toggle("is-scrolled", window.scrollY > 12);
}

function focusableElements() {
  return Array.from(
    modalPanel.querySelectorAll(
      'a[href], button:not([disabled]), details > summary, [tabindex]:not([tabindex="-1"])'
    )
  );
}

function openModal(trigger) {
  returnFocusTo = trigger;
  modal.hidden = false;
  document.body.classList.add("modal-open");
  modalPanel.focus();
}

function closeModal() {
  if (modal.hidden) {
    return;
  }

  modal.hidden = true;
  document.body.classList.remove("modal-open");

  if (returnFocusTo) {
    returnFocusTo.focus();
  }
}

function beginDownload(event) {
  const trigger = event.currentTarget;

  if (!DOWNLOAD_AVAILABLE) {
    downloadStatus.hidden = false;
    downloadStatus.scrollIntoView({ behavior: "smooth", block: "nearest" });
    downloadStatus.focus?.();
    return;
  }

  const downloadLink = document.createElement("a");
  downloadLink.href = DOWNLOAD_URL;
  downloadLink.download = "";
  document.body.appendChild(downloadLink);
  downloadLink.click();
  downloadLink.remove();
  openModal(trigger);
}

function handleModalKeydown(event) {
  if (event.key === "Escape") {
    closeModal();
    return;
  }

  if (event.key !== "Tab") {
    return;
  }

  const focusable = focusableElements();
  const first = focusable[0];
  const last = focusable[focusable.length - 1];

  if (event.shiftKey && (document.activeElement === first || document.activeElement === modalPanel)) {
    event.preventDefault();
    last.focus();
  } else if (!event.shiftKey && document.activeElement === last) {
    event.preventDefault();
    first.focus();
  }
}

window.addEventListener("scroll", updateHeader, { passive: true });
downloadButtons.forEach((button) => button.addEventListener("click", beginDownload));
closeButtons.forEach((button) => button.addEventListener("click", closeModal));
modal.addEventListener("keydown", handleModalKeydown);

updateHeader();
