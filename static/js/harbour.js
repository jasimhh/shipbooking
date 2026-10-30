// Harbour master: renders the live map and operations panel from server data.
// Ferry positions are estimated from each sailing's timetable and refreshed every 30 seconds.
(() => {
  const D = JSON.parse(document.getElementById("harbour-data").textContent);
  const offset = Date.parse(D.now) - Date.now(); // trust the server clock, not the browser's
  const BOARDING_MS = 30 * 60 * 1000;
  const reduceMotion = matchMedia("(prefers-reduced-motion: reduce)").matches;
  const $ = (id) => document.getElementById(id);
  const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const icon = (name) => `<svg class="i" aria-hidden="true"><use href="#${name}"/></svg>`;
  const inr = (n) => "₹" + Number(n).toLocaleString("en-IN", { maximumFractionDigits: 0 });

  const S = { region: 0, sailing: null, tab: "alerts", zoom: 1, pax: {}, paxFilter: "all", sailFilter: "all", query: "", person: 0 };

  // ---- sailing state (mirrors apps/staff/charts.sailing_state) ----
  function live(s) {
    if (s.state === "cancelled") return { state: "cancelled", progress: 0 };
    const now = Date.now() + offset, dep = Date.parse(s.dep), arr = Date.parse(s.arr);
    if (now >= arr) return { state: "arrived", progress: 1 };
    if (now >= dep) return { state: "at_sea", progress: Math.min(1, (now - dep) / (arr - dep)) };
    if (dep - now <= BOARDING_MS) return { state: "boarding", progress: 0 };
    return { state: "scheduled", progress: 0 };
  }
  const STATE = {
    at_sea: ["At sea", "sea"], boarding: ["Boarding", "ok"], scheduled: ["Scheduled", "mute"],
    arrived: ["Arrived", "mute"], cancelled: ["Cancelled", "bad"],
  };
  function badge(s) {
    const st = live(s).state;
    if (s.delayed && (st === "scheduled" || st === "boarding")) return ["Delayed", "warn"];
    return STATE[st];
  }
  const region = () => D.regions[S.region];
  const sailing = () => region()?.sailings.find((s) => s.id === S.sailing);

  const RANK = { at_sea: 0, boarding: 1, scheduled: 2, arrived: 3, cancelled: 4 };
  const bestSailing = (list) => [...list].sort((a, b) => RANK[live(a).state] - RANK[live(b).state])[0];
  function pickDefaultSailing() {
    const best = bestSailing(region()?.sailings || []);
    S.sailing = best ? best.id : null;
  }
  // On first load open the area with the liveliest sailing (at sea, then boarding, then next to leave).
  function pickDefaultRegion() {
    const score = (r) => (r.sailings.length ? RANK[live(bestSailing(r.sailings)).state] : 9);
    D.regions.forEach((r, i) => { if (score(r) < score(D.regions[S.region])) S.region = i; });
  }

  // ---- map ----
  function drawMap() {
    const r = region(), el = $("map");
    if (!r) {
      el.innerHTML = `<div class="empty-map"><p>No routes yet.<br>Add ports, routes and sailings in the admin to see them here.</p></div>`;
      return;
    }
    const sel = sailing();
    const a = r.art;
    const art = a ? `
      <g fill="var(--landfill)" stroke="var(--coast)" stroke-width="1.6" stroke-linejoin="round">${a.land.map((p) => `<path d="${p}"/>`).join("")}</g>
      <g fill="none" stroke="var(--coast)" stroke-width=".8" opacity=".35" stroke-dasharray="1 5">${a.land.map((p) => `<path d="${p}" transform="translate(10 8)"/>`).join("")}</g>
      ${a.places.map((p) => `<text class="place" x="${p[1]}" y="${p[2]}">${esc(p[0])}</text>`).join("")}
      ${a.depths.map((p) => `<text class="depth" x="${p[0]}" y="${p[1]}">${esc(p[2])}</text>`).join("")}
      ${a.lights.map((p) => `<g transform="translate(${p[0]} ${p[1]})"><path d="M0 -10 L5 4 H-5Z" fill="var(--coast)"/><circle r="14" fill="none" stroke="var(--coast)" stroke-width=".6" stroke-dasharray="2 3"/></g>`).join("")}` : "";
    const routes = r.routes.map((rt) => {
      const on = sel && sel.route === rt.id;
      return `<path id="rt${rt.id}" d="${rt.path}" fill="none" stroke="var(${on ? "--route" : "--other"})" stroke-width="${on ? 3 : 1.5}" stroke-dasharray="${on ? "10 7" : "2 5"}" stroke-linecap="round"/>`;
    }).join("");
    const ports = r.ports.map((p) => {
      const left = p.x > 760, tx = left ? p.x - 16 : p.x + 16, anchor = left ? "end" : "start";
      return `<g><circle cx="${p.x}" cy="${p.y}" r="8" fill="var(--paper)" stroke="var(--ink)" stroke-width="2"/>
        <path d="M${p.x - 15} ${p.y}h30M${p.x} ${p.y - 15}v30" stroke="var(--ink)" stroke-width=".8" opacity=".6"/>
        <text class="port" x="${tx}" y="${p.y + 24}" text-anchor="${anchor}">${esc(p.name)}</text>
        <text class="coord" x="${tx}" y="${p.y + 38}" text-anchor="${anchor}">${esc(p.coord)}</text></g>`;
    }).join("");
    el.innerHTML = `<svg viewBox="0 0 1000 600" preserveAspectRatio="xMidYMid slice">
      <g id="vp" style="transform-origin:500px 300px;transform:scale(${S.zoom})">${art}${routes}${ports}<g id="boats"></g></g>
      <g transform="translate(60 120)" stroke="var(--ink)" fill="none" opacity=".8"><circle r="26"/><circle r="20" stroke-dasharray="1 4"/><path d="M0 -34 L5 0 L0 34 L-5 0Z" fill="var(--ink)"/><text x="-4" y="-38" class="coord" stroke="none" fill="var(--ink)">N</text></g></svg>`;
    placeBoats();
  }

  function placeBoats() {
    const r = region(), g = $("boats");
    if (!r || !g) return;
    const ns = "http://www.w3.org/2000/svg";
    g.replaceChildren();
    for (const s of r.sailings) {
      const { state, progress } = live(s);
      if (state !== "at_sea" && state !== "boarding") continue;
      const path = $("rt" + s.route);
      if (!path) continue;
      const pt = path.getPointAtLength(path.getTotalLength() * progress);
      const on = s.id === S.sailing, color = state === "boarding" ? "var(--ok)" : "var(--route)";
      const boat = document.createElementNS(ns, "g");
      boat.setAttribute("class", "boat");
      boat.setAttribute("transform", `translate(${pt.x.toFixed(1)} ${pt.y.toFixed(1)})`);
      boat.setAttribute("tabindex", "0");
      boat.setAttribute("role", "button");
      boat.setAttribute("aria-label", `${s.vessel}, ${STATE[state][0].toLowerCase()}, ${s.label}`);
      boat.innerHTML = `${state === "boarding" && !reduceMotion ? `<circle r="18" fill="none" stroke="${color}" stroke-width="2" opacity=".6"><animate attributeName="r" values="12;22;12" dur="2.4s" repeatCount="indefinite"/></circle>` : ""}
        <rect x="-12" y="-8" width="24" height="16" rx="3" fill="var(--paper)" stroke="${color}" stroke-width="${on ? 3.5 : 2.5}"/><circle r="3.5" fill="${color}"/>`;
      const select = () => { S.sailing = s.id; S.person = 0; renderAll(); };
      boat.addEventListener("click", select);
      boat.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); select(); } });
      g.appendChild(boat);
    }
  }

  function ferryCard() {
    const s = sailing(), el = $("fc");
    if (!s) { el.hidden = true; return; }
    el.hidden = false;
    const { state } = live(s);
    const short = s.vessel.replace(/^(MV|MS|MT)\s+/i, "").split(/\s+/).map((w) => w[0]).join("").slice(0, 3).toUpperCase();
    const [label] = badge(s);
    const eta = state === "at_sea" ? ["Arrives", s.arrives] : state === "arrived" ? ["Arrived", s.arrives] : state === "cancelled" ? ["Was due", s.time] : ["Departs", s.time];
    el.innerHTML = `<span class="id">${esc(short)}</span><span><b>${esc(s.vessel)}</b><small>${esc(label)} · ${s.sold}/${s.capacity} · ${esc(s.label)}</small></span>
      <span class="eta"><small>${eta[0]}</small><b>${esc(eta[1])}</b></span>`;
  }

  // ---- panel ----
  function stats() {
    const t = D.stats;
    const third = D.money ? `<div class="stat"><small>Received today</small><b>${inr(t.received)}</b><em class="mute" style="background:none">payments</em></div>`
                         : `<div class="stat"><small>Cancelled</small><b>${t.cancelled}</b><em style="color:var(--bad)">today</em></div>`;
    $("stats").innerHTML = `<div class="stat"><small>Sailings today</small><b>${t.sailings}</b><em style="color:var(--warn)">${t.delayed} delayed</em></div>
      <div class="stat"><small>Passengers</small><b>${t.passengers}</b><em style="color:var(--dim)">confirmed</em></div>${third}
      <div class="stat"><small>Open issues</small><b>${t.issues}</b><em style="color:${t.issues ? "var(--bad)" : "var(--ok)"}">${t.issues ? "need action" : "all clear"}</em></div>`;
    $("alertCount").textContent = D.alerts.length || "";
  }

  function chips(names, current, key) {
    return names.map(([v, l]) => `<button class="fchip" type="button" data-${key}="${v}" aria-pressed="${v === current}">${l}</button>`).join("");
  }

  function tools() {
    const el = $("tools");
    if (S.tab === "pax") {
      el.innerHTML = `<label class="search">${icon("search")}<input id="q" value="${esc(S.query)}" placeholder="Name, booking or phone" aria-label="Search passengers"></label>
        ${chips([["all", "All"], ["waiting", "Not boarded"], ["issues", "Issues"]], S.paxFilter, "pf")}`;
      $("q").addEventListener("input", (e) => { S.query = e.target.value; S.person = 0; list(); });
      el.querySelectorAll("[data-pf]").forEach((b) => b.onclick = () => { S.paxFilter = b.dataset.pf; S.person = 0; tools(); list(); });
    } else if (S.tab === "sail") {
      el.innerHTML = chips([["all", "All today"], ["delayed", "Delayed"], ["sea", "At sea"]], S.sailFilter, "sf");
      el.querySelectorAll("[data-sf]").forEach((b) => b.onclick = () => { S.sailFilter = b.dataset.sf; tools(); list(); });
    } else el.innerHTML = "";
  }

  function detail(p) {
    const el = $("detail");
    if (!p) { el.hidden = true; el.innerHTML = ""; return; }
    const s = sailing();
    el.hidden = false;
    el.innerHTML = `<div class="dh"><span class="av">${esc(p.initials)}</span><div><h3>${esc(p.name)}</h3><small>${esc(p.age)} · ${esc(p.gender)} · <span class="mono">${esc(p.booking)}</span></small></div></div>
      <div class="sect"><h4>Journey</h4><dl class="kv"><dt>Sailing</dt><dd>${esc(s.time)} ${esc(s.label)}</dd><dt>Class</dt><dd>${esc(p.cabin)}</dd><dt>Ticket</dt><dd><span class="st ${p.state}">${esc(p.ticket)}</span></dd></dl></div>
      <div class="sect"><h4>Contact</h4><dl class="kv"><dt>Email</dt><dd>${esc(p.email)}</dd><dt>Mobile</dt><dd class="mono">${esc(p.phone)}</dd></dl></div>
      <div class="sect"><h4>Payment</h4><dl class="kv"><dt>Status</dt><dd>${esc(p.payment)}</dd></dl></div>
      <div class="acts">${p.admin_url ? `<a class="btn" href="${esc(p.admin_url)}">Open booking</a>` : ""}<a class="btn ghost" href="tel:${esc(p.phone.replace(/[^+\d]/g, ""))}">Call</a></div>`;
  }

  async function loadPax(s) {
    if (S.pax[s.id]) return S.pax[s.id];
    const res = await fetch(s.passengers, { credentials: "same-origin", headers: { Accept: "application/json" } });
    if (!res.ok) throw new Error(res.status);
    return (S.pax[s.id] = (await res.json()).passengers);
  }

  async function list() {
    const el = $("list");
    detail(null);
    if (S.tab === "alerts") {
      el.innerHTML = D.alerts.length ? D.alerts.map((a) => {
        const tag = a.url ? "a" : "div";
        return `<${tag} class="alert lv-${a.level}"${a.url ? ` href="${esc(a.url)}"` : ""}><span style="color:var(--${a.level})">${icon(a.icon)}</span><span><b>${esc(a.title)}</b><small>${esc(a.detail)}</small></span></${tag}>`;
      }).join("") : `<p class="muted">Nothing needs attention right now.</p>`;
      return;
    }
    if (S.tab === "fleet") {
      el.innerHTML = D.fleet.length ? D.fleet.map((f) => `<div class="item"><span class="av">${icon("ticket")}</span><span><b>${esc(f.name)}</b><small>${esc(f.operator)} · ${f.capacity} places · ${esc(f.seating)}</small></span><span class="st ${f.active ? "ok" : "warn"}">${f.active ? "In service" : "Inactive"}</span></div>`).join("")
                                    : `<p class="muted">No ferries yet.</p>`;
      return;
    }
    const r = region();
    if (S.tab === "sail") {
      let rows = r ? r.sailings : [];
      if (S.sailFilter === "delayed") rows = rows.filter((s) => s.delayed);
      if (S.sailFilter === "sea") rows = rows.filter((s) => live(s).state === "at_sea");
      el.innerHTML = rows.length ? rows.map((s) => {
        const [label, cls] = badge(s);
        return `<button class="item" type="button" data-s="${s.id}" aria-pressed="${s.id === S.sailing}"><span class="time">${esc(s.time)}</span><span><b>${esc(s.label)}</b><small>${esc(s.vessel)} · ${s.sold}/${s.capacity}${s.note ? " · " + esc(s.note) : ""}</small></span><span class="st ${cls}">${label}</span></button>`;
      }).join("") : `<p class="muted">No sailings ${S.sailFilter === "all" ? "today in this area" : "match"}.</p>`;
      el.querySelectorAll("[data-s]").forEach((b) => b.onclick = () => { S.sailing = +b.dataset.s; S.person = 0; renderAll(); });
      return;
    }
    // passengers
    const s = sailing();
    if (!s) { el.innerHTML = `<p class="muted">Choose a sailing first.</p>`; return; }
    if (!s.passengers) { el.innerHTML = `<p class="muted">You don't have access to this sailing's passenger list.</p>`; return; }
    el.innerHTML = `<p class="muted">Loading passengers for ${esc(s.time)} ${esc(s.label)}…</p>`;
    let rows;
    try { rows = await loadPax(s); } catch (e) { el.innerHTML = `<p class="muted">Couldn't load passengers. Refresh to try again.</p>`; return; }
    if (S.tab !== "pax" || sailing() !== s) return; // the user moved on while loading
    const q = S.query.trim().toLowerCase();
    let shown = rows.filter((p) => !q || [p.name, p.booking, p.phone, p.email].some((v) => v.toLowerCase().includes(q)));
    if (S.paxFilter === "waiting") shown = shown.filter((p) => p.state === "ok");
    if (S.paxFilter === "issues") shown = shown.filter((p) => p.state === "bad");
    if (!shown.length) { el.innerHTML = `<p class="muted">${rows.length ? "No passengers match." : "No passengers booked on this sailing yet."}</p>`; return; }
    S.person = Math.min(S.person, shown.length - 1);
    el.innerHTML = `<p class="muted" style="padding-top:0">${esc(s.time)} ${esc(s.label)} · ${rows.length} passenger(s)</p>` + shown.map((p, i) =>
      `<button class="item" type="button" data-p="${i}" aria-pressed="${i === S.person}"><span class="av">${esc(p.initials)}</span><span><b>${esc(p.name)}</b><small><span class="mono">${esc(p.booking)}</span> · ${esc(p.age)} · ${esc(p.cabin)}</small></span><span class="st ${p.state}">${esc(p.ticket)}</span></button>`).join("");
    el.querySelectorAll("[data-p]").forEach((b) => b.onclick = () => {
      S.person = +b.dataset.p;
      el.querySelectorAll("[data-p]").forEach((x) => x.setAttribute("aria-pressed", x === b));
      detail(shown[S.person]);
    });
    detail(shown[S.person]);
  }

  function regionsBar() {
    $("regions").innerHTML = D.regions.map((r, i) => `<button type="button" data-r="${i}" aria-pressed="${i === S.region}">${esc(r.label)}</button>`).join("") || `<span class="muted" style="padding:4px 8px">No areas</span>`;
    $("regions").querySelectorAll("[data-r]").forEach((b) => b.onclick = () => { S.region = +b.dataset.r; S.zoom = 1; S.person = 0; pickDefaultSailing(); renderAll(); });
  }

  function renderAll() {
    regionsBar(); drawMap(); ferryCard(); tools(); list();
    document.querySelectorAll("[data-tab]").forEach((b) => b.setAttribute("aria-selected", b.dataset.tab === S.tab));
  }

  // ---- controls ----
  document.querySelectorAll("[data-tab]").forEach((b) => b.onclick = () => { S.tab = b.dataset.tab; S.person = 0; renderAll(); });
  document.querySelectorAll("[data-z]").forEach((b) => b.onclick = () => {
    S.zoom = +b.dataset.z ? Math.min(2.2, Math.max(0.8, S.zoom * +b.dataset.z)) : 1;
    const vp = $("vp"); if (vp) vp.style.transform = `scale(${S.zoom})`;
  });
  const themeBtn = $("theme");
  const syncTheme = () => {
    const day = document.documentElement.dataset.theme === "day";
    themeBtn.innerHTML = icon(day ? "moon" : "sun");
    themeBtn.setAttribute("aria-label", day ? "Switch to dark blueprint" : "Switch to light whiteprint");
  };
  themeBtn.onclick = () => {
    const day = document.documentElement.dataset.theme !== "day";
    document.documentElement.dataset.theme = day ? "day" : "night";
    try { localStorage.setItem("harbour-theme", day ? "day" : "night"); } catch (e) {}
    syncTheme();
  };
  syncTheme();

  const drawer = $("drawer");
  if (drawer) {
    const close = () => drawer.classList.remove("open");
    $("add").onclick = () => { drawer.classList.add("open"); drawer.querySelector("input").focus(); };
    $("close").onclick = close;
    drawer.addEventListener("click", (e) => { if (e.target === drawer) close(); });
    document.addEventListener("keydown", (e) => { if (e.key === "Escape") close(); });
  }

  const tick = () => { $("clockTime").textContent = new Date(Date.now() + offset).toLocaleTimeString("en-GB", { timeZone: "Asia/Kolkata", hour: "2-digit", minute: "2-digit" }); };
  tick();
  setInterval(() => { tick(); placeBoats(); ferryCard(); }, 30000);

  if (D.regions.length) pickDefaultRegion();
  pickDefaultSailing();
  stats();
  renderAll();
})();
