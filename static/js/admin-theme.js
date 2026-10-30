// The admin follows the site's day (white) / night (blueprint) choice instead of its own toggle.
try { document.documentElement.dataset.theme = localStorage.getItem("harbour-theme") === "night" ? "dark" : "light"; } catch (e) {}
