// Admins: press Shift+A anywhere (outside a text box) to open the admin panel.
(() => {
  const url = document.body.dataset.adminUrl;
  if (!url) return;
  document.addEventListener("keydown", (e) => {
    if (!e.shiftKey || e.ctrlKey || e.metaKey || e.altKey || e.key.toLowerCase() !== "a") return;
    if (e.target.closest("input, textarea, select, [contenteditable]")) return;
    e.preventDefault();
    window.location.href = url;
  });
})();
