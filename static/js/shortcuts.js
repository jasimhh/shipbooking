// Admins: press G then A anywhere (outside a text box) to open the admin panel.
(() => {
  const url = document.body.dataset.adminUrl;
  if (!url) return;
  let last = "", at = 0;
  document.addEventListener("keydown", (e) => {
    if (e.ctrlKey || e.metaKey || e.altKey || e.target.closest("input, textarea, select, [contenteditable]")) return;
    const key = e.key.toLowerCase(), now = Date.now();
    if (last === "g" && key === "a" && now - at < 1500) window.location.href = url;
    last = key;
    at = now;
  });
})();
