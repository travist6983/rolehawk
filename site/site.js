// Small progressive enhancements. The page works fully without this file.
// No network requests, no storage, no tracking.
(function () {
  "use strict";

  var status = document.querySelector(".sr-status");

  // Copy buttons on the install commands.
  document.querySelectorAll("[data-copy]").forEach(function (btn) {
    if (!navigator.clipboard) return;
    btn.hidden = false;
    btn.setAttribute("aria-label", "Copy the " + btn.closest(".cmd").querySelector(".cmd-label").textContent.trim() + " command");
    btn.addEventListener("click", function () {
      var code = document.getElementById(btn.getAttribute("data-copy"));
      navigator.clipboard.writeText(code.textContent.trim()).then(
        function () {
          btn.textContent = "Copied";
          if (status) status.textContent = "Command copied";
          setTimeout(function () {
            btn.textContent = "Copy";
            if (status) status.textContent = "";
          }, 2000);
        },
        function () {
          // Clipboard refused: select the command so the visitor can copy it by hand.
          var range = document.createRange();
          range.selectNodeContents(code);
          var sel = window.getSelection();
          sel.removeAllRanges();
          sel.addRange(range);
        },
      );
    });
  });

  // Pause and play the animated screenshots. Visitors who prefer reduced motion start paused
  // (the <source> elements already show stills without JavaScript).
  var toggle = document.querySelector("[data-motion-toggle]");
  var pictures = document.querySelectorAll("picture.anim");
  if (!toggle || !pictures.length) return;

  function setPaused(paused) {
    pictures.forEach(function (pic) {
      var img = pic.querySelector("img");
      var src = paused ? img.getAttribute("data-still") : img.getAttribute("data-anim");
      pic.querySelectorAll("source").forEach(function (s) {
        s.srcset = src;
      });
      img.src = src;
    });
    toggle.setAttribute("data-paused", paused ? "true" : "false");
    toggle.textContent = paused ? "Play animations" : "Pause animations";
  }

  var reduce = window.matchMedia("(prefers-reduced-motion: reduce)");
  toggle.hidden = false;
  if (reduce.matches) setPaused(true);
  toggle.addEventListener("click", function () {
    setPaused(toggle.getAttribute("data-paused") !== "true");
  });
})();
