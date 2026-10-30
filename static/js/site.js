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

// Route maps: place the ferry where the timetable says it should be (estimate, not GPS) and say how far along it is.
const reduceMotion = matchMedia("(prefers-reduced-motion: reduce)").matches;
const routeOf = (el) => document.getElementById(el.dataset.route || el.querySelector("mpath").getAttribute("href").slice(1));
const placeOn = (el, path, progress) => {
  const pt = path.getPointAtLength(path.getTotalLength() * progress);
  el.setAttribute("transform", `translate(${pt.x.toFixed(1)} ${pt.y.toFixed(1)})`);
};
if (reduceMotion) {
  document.querySelectorAll(".chart-boat animateMotion").forEach((anim) => {
    const boat = anim.parentNode;
    placeOn(boat, routeOf(anim), 0.5);
    anim.remove();
  });
}
document.querySelectorAll("[data-live]").forEach((boat) => {
  const path = routeOf(boat), text = boat.closest(".chart").querySelector("[data-live-text]");
  const dep = Date.parse(boat.dataset.dep), arr = Date.parse(boat.dataset.arr);
  const span = (ms) => {
    const m = Math.max(1, Math.round(ms / 60000)), d = Math.floor(m / 1440), h = Math.floor((m % 1440) / 60), mm = m % 60;
    return d ? `${d} d ${h} h` : h ? `${h} h ${mm} min` : `${mm} min`;
  };
  const clock = (t) => new Date(t).toLocaleTimeString("en-GB", { timeZone: "Asia/Kolkata", hour: "2-digit", minute: "2-digit" });
  const tick = () => {
    if (boat.dataset.status === "cancelled") { text.textContent = "This sailing is cancelled."; return; }
    const now = Date.now(), delayed = boat.dataset.status === "delayed" ? "Delayed · " : "";
    let progress = 0, msg;
    if (now < dep) msg = `${delayed}Departs in ${span(dep - now)}${dep - now <= 30 * 60000 ? " · boarding now" : ""}`;
    else if (now < arr) { progress = (now - dep) / (arr - dep); msg = `${delayed}At sea · about ${Math.round(progress * 100)}% of the way · arrives ${clock(arr)}`; }
    else { progress = 1; msg = "Arrived"; }
    placeOn(boat, path, progress);
    boat.removeAttribute("hidden");
    boat.classList.toggle("docked", progress === 0 || progress === 1);
    text.textContent = `${msg} (estimated from the timetable, not GPS)`;
  };
  tick();
  setInterval(tick, 30000);
});

// Journey preview: as From and To are picked, show that area's map with the crossing between the two jetties.
document.querySelectorAll("[data-journey]").forEach((fig) => {
  const form = fig.previousElementSibling, from = form.elements.origin, to = form.elements.destination;
  const text = fig.querySelector("[data-journey-text]");
  const port = (code) => code && fig.querySelector(`[data-code="${CSS.escape(code)}"]`);
  const name = (sel) => sel.options[sel.selectedIndex].text;
  const update = () => {
    const a = port(from.value), b = port(to.value), svg = (a || b)?.closest("svg");
    fig.querySelectorAll("svg").forEach((s) => s.toggleAttribute("hidden", svg ? s !== svg : s !== fig.querySelector("svg")));
    fig.querySelectorAll(".chart-port").forEach((p) => p.classList.toggle("picked", p === a || p === b));
    fig.querySelectorAll(".journey-line, .journey-boat").forEach((el) => el.setAttribute("hidden", ""));
    if (!a || !b) {
      text.textContent = a ? `Leaving from ${name(from)}. Now pick where you're going.` : b ? `Going to ${name(to)}. Now pick where you're leaving from.` : "Pick where you're leaving from and going to, and your crossing appears here.";
      return;
    }
    if (a === b) { text.textContent = "Pick two different jetties."; return; }
    if (a.closest("svg") !== b.closest("svg")) { text.textContent = `${name(from)} and ${name(to)} are in different areas, so no ferry crosses between them.`; return; }
    const [x1, y1, x2, y2] = [a.dataset.x, a.dataset.y, b.dataset.x, b.dataset.y].map(Number);
    const cx = (x1 + x2) / 2 - (y2 - y1) * 0.18, cy = (y1 + y2) / 2 + (x2 - x1) * 0.18;  // same curve as the route maps
    const line = svg.querySelector(".journey-line"), boat = svg.querySelector(".journey-boat");
    line.setAttribute("d", `M${x1} ${y1} Q${cx.toFixed(0)} ${cy.toFixed(0)} ${x2} ${y2}`);
    line.removeAttribute("hidden");
    boat.setAttribute("transform", `translate(${x1} ${y1})`);
    boat.removeAttribute("hidden");
    text.textContent = `Your crossing: ${name(from)} to ${name(to)}. Search to see sailings on this route.`;
  };
  from.addEventListener("change", update);
  to.addEventListener("change", update);
  update();
});
