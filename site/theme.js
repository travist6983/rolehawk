// Applies the visitor's saved Light / Dark choice before first paint, like the app's
// index.html. With no saved choice the page follows the system setting through CSS.
(function () {
  "use strict";
  var pref = null;
  try {
    pref = localStorage.getItem("rolehawk.site.theme");
  } catch (e) {
    pref = null;
  }
  if (pref === "light" || pref === "dark") {
    document.documentElement.classList.add(pref);
  }
})();
