// Show/hide toggle for every password field. Progressive enhancement: without JS the field still works.
document.querySelectorAll('input[type="password"]').forEach((input) => {
  const wrap = document.createElement("div");
  wrap.className = "password-wrap";
  input.parentNode.insertBefore(wrap, input);
  wrap.appendChild(input);

  const button = document.createElement("button");
  button.type = "button";
  button.className = "password-toggle";
  button.textContent = "Show";
  button.setAttribute("aria-label", "Show password");
  button.setAttribute("aria-pressed", "false");
  button.addEventListener("click", () => {
    const show = input.type === "password";
    input.type = show ? "text" : "password";
    button.textContent = show ? "Hide" : "Show";
    button.setAttribute("aria-label", show ? "Hide password" : "Show password");
    button.setAttribute("aria-pressed", String(show));
    input.focus();
  });
  wrap.appendChild(button);
});

// Live "m:ss" left on reservation holds.
document.querySelectorAll("[data-countdown]").forEach((el) => {
  const end = new Date(el.dataset.countdown).getTime();
  const tick = () => {
    const s = Math.max(0, Math.round((end - Date.now()) / 1000));
    el.textContent = s ? `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}` : "no time";
    if (s) setTimeout(tick, 1000);
  };
  tick();
});

// Night (blueprint) / day (whiteprint) switch, remembered per browser.
document.querySelectorAll("[data-theme-toggle]").forEach((button) => {
  const sync = () => {
    const day = document.documentElement.dataset.theme === "day";
    button.setAttribute("aria-pressed", String(day));
    button.querySelector("use").setAttribute("href", day ? "#i-moon" : "#i-sun");
  };
  button.addEventListener("click", () => {
    const day = document.documentElement.dataset.theme !== "day";
    document.documentElement.dataset.theme = day ? "day" : "night";
    try { localStorage.setItem("harbour-theme", day ? "day" : "night"); } catch (e) {}
    sync();
  });
  sync();
});

// Confirmation before destructive form posts, and print buttons (no inline handlers, so CSP can block inline script).
document.querySelectorAll("form[data-confirm]").forEach((form) => {
  form.addEventListener("submit", (e) => { if (!confirm(form.dataset.confirm)) e.preventDefault(); });
});
document.querySelectorAll("[data-print]").forEach((button) => button.addEventListener("click", () => window.print()));
