// Loaded in <head> before paint so the chosen theme never flashes. Same key as the Harbour Master map.
try { if (localStorage.getItem("harbour-theme") === "day") document.documentElement.dataset.theme = "day"; } catch (e) {}
