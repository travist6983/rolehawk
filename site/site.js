// Small progressive enhancements: the demos come alive, and copy buttons appear. The page reads
// fully without this file. No network requests and no tracking; the only thing stored is the
// Light / Dark choice.
(function () {
  "use strict";

  var root = document.documentElement;
  var status = document.querySelector("[data-status]");
  var isMac = /Mac|iPhone|iPad|iPod/.test(navigator.platform || navigator.userAgent || "");
  var each = function (list, fn) {
    Array.prototype.forEach.call(list, fn);
  };

  function say(text) {
    if (status) status.textContent = text;
  }

  // Controls that only work with JavaScript start hidden.
  each(document.querySelectorAll("[data-js-only]"), function (el) {
    el.hidden = false;
  });

  // Shortcut labels for this visitor's keyboard, as the app shows them.
  each(document.querySelectorAll("[data-mod-key]"), function (el) {
    el.textContent = isMac ? "⌘K" : "Ctrl K";
  });
  each(document.querySelectorAll("[data-alt-key]"), function (el) {
    el.textContent = isMac ? "⌥" : "Alt";
  });

  // Theme: the footer's Light / Dark switch.
  var osDark = window.matchMedia("(prefers-color-scheme: dark)");
  var toggle = document.querySelector(".theme-toggle");
  function syncTheme() {
    var dark = root.classList.contains("dark") || (!root.classList.contains("light") && osDark.matches);
    if (!toggle) return;
    each(toggle.querySelectorAll("button"), function (b) {
      b.setAttribute("aria-pressed", String((b.getAttribute("data-theme-choice") === "dark") === dark));
    });
  }
  if (toggle) {
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

  // Phone menu: close after picking a section, on Escape, or on a click elsewhere.
  var menu = document.querySelector(".menu");
  if (menu) {
    menu.addEventListener("click", function (event) {
      if (event.target.closest("a")) menu.open = false;
    });
    document.addEventListener("keydown", function (event) {
      if (event.key === "Escape" && menu.open) {
        menu.open = false;
        menu.querySelector("summary").focus();
      }
    });
    document.addEventListener("click", function (event) {
      if (menu.open && !menu.contains(event.target)) menu.open = false;
    });
  }

  // Fit scale position, as in the app: 50 sits at the left edge, 100 at the right.
  function fitPct(fit) {
    return Math.max(0, Math.min(100, (fit - 50) * 2)) + "%";
  }

  // The pipeline board: drag a card, or focus it and press Alt (Option) with an arrow key.
  (function board() {
    var el = document.querySelector("[data-board]");
    if (!el) return;
    var STAGES = ["Saved", "Applying", "Applied", "Screen", "Interview", "Offer"];
    var NEXT = [
      "Write your application",
      "Check 1 flagged line",
      "Waiting to hear back",
      "Reply to the recruiter",
      "Prepare for the interview",
      "Decide on the offer",
    ];
    var cols = el.querySelectorAll("[data-stage]");
    var note = el.querySelector("[data-board-note]");
    var dragging = null;

    function stageOf(card) {
      return Number(card.closest("[data-stage]").getAttribute("data-stage"));
    }
    function setOver(col) {
      each(cols, function (c) {
        c.classList.toggle("is-over", c === col);
      });
    }
    function move(card, to) {
      to = Math.max(0, Math.min(STAGES.length - 1, to));
      if (stageOf(card) === to) return;
      var hadFocus = document.activeElement === card;
      cols[to].querySelector("[data-cards]").appendChild(card);
      var next = card.querySelector("[data-next]");
      next.textContent = NEXT[to];
      next.classList.toggle("is-waiting", to === 2);
      each(cols, function (col) {
        col.querySelector("[data-col-count]").textContent = String(col.querySelectorAll("[data-card]").length);
      });
      var co = card.querySelector("[data-co]").textContent;
      note.textContent =
        to === STAGES.length - 1
          ? co + " made it to Offer. That's the whole idea."
          : co + " moved to " + STAGES[to] + ". Next: " + NEXT[to].toLowerCase() + ".";
      if (hadFocus) card.focus();
    }

    el.addEventListener("dragstart", function (event) {
      var card = event.target.closest && event.target.closest("[data-card]");
      if (!card) return;
      dragging = card;
      card.classList.add("is-dragging");
      event.dataTransfer.effectAllowed = "move";
      event.dataTransfer.setData("text/plain", card.querySelector("[data-co]").textContent);
    });
    el.addEventListener("dragend", function () {
      if (dragging) dragging.classList.remove("is-dragging");
      dragging = null;
      setOver(null);
    });
    el.addEventListener("dragleave", function (event) {
      if (!event.relatedTarget || !el.contains(event.relatedTarget)) setOver(null);
    });
    each(cols, function (col) {
      col.addEventListener("dragover", function (event) {
        if (!dragging) return;
        event.preventDefault();
        event.dataTransfer.dropEffect = "move";
        setOver(col);
      });
      col.addEventListener("drop", function (event) {
        if (!dragging) return;
        event.preventDefault();
        move(dragging, Number(col.getAttribute("data-stage")));
        setOver(null);
      });
    });
    el.addEventListener("keydown", function (event) {
      var card = event.target.closest && event.target.closest("[data-card]");
      if (!card || !event.altKey || (event.key !== "ArrowLeft" && event.key !== "ArrowRight")) return;
      event.preventDefault();
      move(card, stageOf(card) + (event.key === "ArrowRight" ? 1 : -1));
    });
  })();

  // Profile review: count the checked rows.
  (function profile() {
    var box = document.querySelector("[data-profile]");
    if (!box) return;
    var count = box.querySelector("[data-profile-count]");
    var inputs = box.querySelectorAll("input[type=checkbox]");
    function update() {
      var n = 0;
      each(inputs, function (input) {
        if (input.checked) n += 1;
      });
      count.textContent = String(n);
    }
    box.addEventListener("change", update);
    update();
  })();

  // Discover: pick a job to see why it scored the way it did.
  (function discover() {
    var box = document.querySelector("[data-discover]");
    if (!box) return;
    var jobs = box.querySelectorAll("[data-job]");
    var value = box.querySelector("[data-fit-value]");
    var word = box.querySelector("[data-fit-word]");
    var mark = box.querySelector("[data-fit-mark]");
    var reasons = box.querySelectorAll("[data-reasons]");
    each(jobs, function (btn) {
      btn.addEventListener("click", function () {
        var id = btn.getAttribute("data-job");
        var score = Number(btn.getAttribute("data-score"));
        each(jobs, function (b) {
          b.setAttribute("aria-pressed", String(b === btn));
        });
        value.textContent = String(score);
        word.textContent = score >= 90 ? "Strong fit" : score >= 80 ? "Good fit" : "Fair fit";
        mark.setAttribute("x", fitPct(score));
        each(reasons, function (list) {
          list.hidden = list.getAttribute("data-reasons") !== id;
        });
      });
    });
  })();

  // Apply: resolve the flagged line, then replay.
  (function factCheck() {
    var box = document.querySelector("[data-factcheck]");
    if (!box) return;
    var count = box.querySelector("[data-fixed-count]");
    box.addEventListener("click", function (event) {
      var btn = event.target.closest("[data-flag]");
      if (!btn) return;
      var choice = btn.getAttribute("data-flag");
      var open = choice === "open";
      if (!open) count.textContent = choice === "keep" ? "40+" : "30+";
      each(box.querySelectorAll("[data-when]"), function (el) {
        el.hidden = (el.getAttribute("data-when") === "open") !== open;
      });
      var focus = box.querySelector(open ? "[data-flag=fixed]" : "[data-flag=open]");
      if (focus) focus.focus();
    });
  })();

  // Ask Claude: pick a question to see the answer.
  (function chat() {
    var box = document.querySelector("[data-chat]");
    if (!box) return;
    var chips = box.querySelectorAll("[data-chat-chip]");
    var pairs = box.querySelectorAll("[data-chat-pair]");
    each(chips, function (chip) {
      chip.addEventListener("click", function () {
        var id = chip.getAttribute("data-chat-chip");
        each(chips, function (c) {
          c.setAttribute("aria-pressed", String(c === chip));
        });
        each(pairs, function (p) {
          p.hidden = p.getAttribute("data-chat-pair") !== id;
        });
      });
    });
  })();

  // Install: show the command for this visitor's system, with a switch for the other one.
  (function install() {
    var box = document.querySelector("[data-install]");
    if (!box) return;
    var tabs = box.querySelectorAll("[data-os]");
    var rows = box.querySelectorAll("[data-os-row]");
    function pick(os) {
      each(tabs, function (t) {
        t.setAttribute("aria-pressed", String(t.getAttribute("data-os") === os));
      });
      each(rows, function (r) {
        r.hidden = r.getAttribute("data-os-row") !== os;
      });
    }
    each(tabs, function (t) {
      t.addEventListener("click", function () {
        pick(t.getAttribute("data-os"));
      });
    });
    pick(/windows/i.test(navigator.userAgent || "") ? "win" : "unix");
  })();

  // Copy buttons: the install commands and the follow-up draft.
  if (!navigator.clipboard) return;
  each(document.querySelectorAll("[data-copy]"), function (btn) {
    var target = document.getElementById(btn.getAttribute("data-copy"));
    if (!target) return;
    var label = btn.textContent;
    var timer = 0;
    btn.hidden = false;
    btn.addEventListener("click", function () {
      var paras = target.querySelectorAll("p");
      var text = paras.length
        ? Array.prototype.map
            .call(paras, function (p) {
              return p.innerText.replace(/\s+\n/g, "\n").trim();
            })
            .join("\n\n")
        : target.textContent.trim();
      navigator.clipboard.writeText(text).then(
        function () {
          btn.textContent = "Copied";
          say(btn.getAttribute("data-copied") || "Copied");
          clearTimeout(timer);
          timer = setTimeout(function () {
            btn.textContent = label;
            say("");
          }, 1800);
        },
        function () {
          // Clipboard refused: select the text so the visitor can copy it by hand.
          var range = document.createRange();
          range.selectNodeContents(target);
          var sel = window.getSelection();
          sel.removeAllRanges();
          sel.addRange(range);
        },
      );
    });
  });
})();
