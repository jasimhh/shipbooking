// The admin follows the site's night (blueprint) / day (whiteprint) choice instead of its own toggle.
try { document.documentElement.dataset.theme = localStorage.getItem("harbour-theme") === "day" ? "light" : "dark"; } catch (e) {}
