/* Applies the saved light/dark choice before first paint (loaded in <head>, not deferred). */
(function () {
  try {
    var t = localStorage.getItem("gitmgf-theme");
    if (t === "light" || t === "dark") document.documentElement.setAttribute("data-theme", t);
  } catch (e) { /* storage blocked: follow the system setting */ }
})();
