// Small progressive enhancements. The page works fully without this file.
// No network requests and no tracking; the only thing stored is the Light / Dark choice.
(function () {
  "use strict";

  var root = document.documentElement;
  var osDark = window.matchMedia("(prefers-color-scheme: dark)");

  function isDark() {
    return root.classList.contains("dark") || (!root.classList.contains("light") && osDark.matches);
  }

  // Theme: the sidebar's Light / Dark switch, and screenshots that have a dark version.
  var toggle = document.querySelector(".theme-toggle");
  function syncTheme() {
    var dark = isDark();
    if (toggle) {
      toggle.querySelectorAll("button").forEach(function (b) {
        b.setAttribute("aria-pressed", String((b.getAttribute("data-theme-choice") === "dark") === dark));
      });
    }
    document.querySelectorAll("img[data-dark]").forEach(function (img) {
      var want = img.getAttribute(dark ? "data-dark" : "data-light");
      if (img.getAttribute("src") !== want) img.setAttribute("src", want);
    });
  }
  if (toggle) {
    toggle.hidden = false;
    toggle.addEventListener("click", function (event) {
      var btn = event.target.closest("button[data-theme-choice]");
      if (!btn) return;
      var choice = btn.getAttribute("data-theme-choice");
      root.classList.remove("light", "dark");
      root.classList.add(choice);
      try {
        localStorage.setItem("rolehawk.site.theme", choice);
      } catch (e) {
        // Storage blocked: the choice lasts for this visit only.
      }
      syncTheme();
    });
  }
  if (osDark.addEventListener) osDark.addEventListener("change", syncTheme);
  syncTheme();

  // Close the phone menu after picking a section.
  var menu = document.querySelector(".menu");
  if (menu) {
    menu.addEventListener("click", function (event) {
      if (event.target.closest("a")) menu.open = false;
    });
  }

  // Highlight the section in view in the sidebar, like the app's active nav item.
  var links = document.querySelectorAll("[data-spy] a[href^='#']");
  if ("IntersectionObserver" in window && links.length) {
    var byId = {};
    links.forEach(function (a) {
      byId[a.getAttribute("href").slice(1)] = a;
    });
    var observer = new IntersectionObserver(
      function (entries) {
        entries.forEach(function (entry) {
          if (!entry.isIntersecting) return;
          links.forEach(function (a) {
            a.removeAttribute("aria-current");
          });
          var link = byId[entry.target.id];
          if (link) link.setAttribute("aria-current", "true");
        });
      },
      { rootMargin: "-30% 0px -60% 0px" },
    );
    Object.keys(byId).forEach(function (id) {
      var section = document.getElementById(id);
      if (section) observer.observe(section);
    });
  }

  // Copy buttons on the install commands.
  var status = document.querySelector("[data-status]");
  document.querySelectorAll("[data-copy]").forEach(function (btn) {
    if (!navigator.clipboard) return;
    btn.hidden = false;
    var code = document.getElementById(btn.getAttribute("data-copy"));
    btn.setAttribute("aria-label", "Copy the " + btn.parentNode.querySelector(".label").textContent + " command");
    btn.addEventListener("click", function () {
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
  var motion = document.querySelector("[data-motion-toggle]");
  var pictures = document.querySelectorAll("picture.anim");
  if (!motion || !pictures.length) return;

  function setPaused(paused) {
    pictures.forEach(function (pic) {
      var img = pic.querySelector("img");
      var src = paused ? img.getAttribute("data-still") : img.getAttribute("data-anim");
      pic.querySelectorAll("source").forEach(function (s) {
        s.srcset = src;
      });
      img.src = src;
    });
    motion.setAttribute("data-paused", paused ? "true" : "false");
    motion.textContent = paused ? "Play animations" : "Pause animations";
  }

  motion.hidden = false;
  if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) setPaused(true);
  motion.addEventListener("click", function () {
    setPaused(motion.getAttribute("data-paused") !== "true");
  });
})();
