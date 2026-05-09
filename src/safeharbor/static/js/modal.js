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
      let dialog = null;
      try {
        dialog = document.querySelector(selector);
      } catch {
        return;
      }
      if (dialog instanceof HTMLDialogElement) {
        event.preventDefault();
        if (!dialog.open) {
          dialog.showModal();
        }
        return;
      }
    }
  }

  const dismiss = target.closest('[data-bs-dismiss="modal"]');
  if (dismiss instanceof HTMLElement) {
    const dialog = dismiss.closest("dialog");
    if (dialog instanceof HTMLDialogElement) {
      // Submit buttons must keep their default form-submission behavior.
      // The form action navigates away from the page; the modal will be
      // discarded with the page, so we do NOT call dialog.close() here.
      const isSubmit = dismiss instanceof HTMLButtonElement && dismiss.type === "submit";
      if (!isSubmit) {
        event.preventDefault();
        dialog.close();
      }
    }
  }
});
