// Native <dialog> shim for Bootstrap modal data-API.
// Intercepts clicks on [data-bs-toggle="modal"][data-bs-target="#X"]
// and [data-bs-dismiss="modal"], delegates to dialog.showModal() / .close().
document.addEventListener("click", (event) => {
  const target = event.target;
  if (!(target instanceof Element)) return;

  const trigger = target.closest('[data-bs-toggle="modal"]');
  if (trigger) {
    const selector = trigger.getAttribute("data-bs-target");
    if (selector) {
      const dialog = document.querySelector(selector);
      if (dialog instanceof HTMLDialogElement) {
        event.preventDefault();
        dialog.showModal();
        return;
      }
    }
  }

  const dismiss = target.closest('[data-bs-dismiss="modal"]');
  if (dismiss) {
    const dialog = dismiss.closest("dialog");
    if (dialog instanceof HTMLDialogElement) {
      event.preventDefault();
      dialog.close();
    }
  }
});
