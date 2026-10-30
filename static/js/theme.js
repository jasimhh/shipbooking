// White "boarding pass" look by default; night blueprint only if chosen. Same key as the Harbour Master map.
try { if (localStorage.getItem("harbour-theme") === "night") document.documentElement.dataset.theme = "night"; } catch (e) {}
