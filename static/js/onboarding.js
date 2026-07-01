/* First-run onboarding: a dismissible welcome + short coachmark tour.
 * Self-contained; runs once per browser (localStorage). Safe no-op if the
 * expected map elements are absent. Replayable via window.ucStartTour(). */
(function () {
  "use strict";
  var KEY = "uc_onboarded_v1";

  var STEPS = [
    {
      sel: ".mode-switcher",
      title: "Two ways to help",
      body: "Switch between <strong>Report Trash</strong> to log litter you spot, and <strong>Cleanup Trash</strong> to fix reported sites.",
    },
    {
      sel: "#report-mode-panel",
      title: "Report a site",
      body: "In Report mode, <strong>Place a Pin</strong> or <strong>Draw an Area</strong> on the map to mark where the trash is.",
    },
    {
      sel: "#mobile-fab-stack",
      title: "Tap to act",
      body: "Use this button to drop a pin, draw an area, or switch to cleanup mode.",
    },
    {
      sel: ".map-legend",
      title: "Read the map",
      body: "Marker colors show each site's status — pending, in progress, or cleaned.",
    },
  ];

  function isVisible(el) {
    return !!(el && el.offsetParent !== null);
  }

  function build(tag, cls, html) {
    var el = document.createElement(tag);
    if (cls) el.className = cls;
    if (html != null) el.innerHTML = html;
    return el;
  }

  function runTour(steps) {
    var i = 0;
    var backdrop = build("div", "onb-backdrop");
    var spot = build("div", "onb-spotlight");
    var pop = build("div", "onb-pop");
    pop.setAttribute("role", "dialog");
    pop.setAttribute("aria-modal", "true");
    pop.setAttribute("aria-labelledby", "onb-title");
    backdrop.appendChild(spot);
    document.body.appendChild(backdrop);
    document.body.appendChild(pop);

    function finish() {
      try { localStorage.setItem(KEY, "1"); } catch (e) {}
      backdrop.remove();
      pop.remove();
      document.removeEventListener("keydown", onKey);
    }

    function onKey(e) {
      if (e.key === "Escape") finish();
      else if (e.key === "Enter") next();
    }
    document.addEventListener("keydown", onKey);

    function render() {
      var step = steps[i];
      var target = document.querySelector(step.sel);
      var r = target.getBoundingClientRect();
      var pad = 8;
      spot.style.top = (r.top - pad) + "px";
      spot.style.left = (r.left - pad) + "px";
      spot.style.width = (r.width + pad * 2) + "px";
      spot.style.height = (r.height + pad * 2) + "px";

      pop.innerHTML =
        '<h3 id="onb-title" class="onb-title">' + step.title + "</h3>" +
        '<p class="onb-body">' + step.body + "</p>" +
        '<div class="onb-actions">' +
        '<span class="onb-count">' + (i + 1) + " / " + steps.length + "</span>" +
        '<div class="onb-btns">' +
        '<button type="button" class="btn btn-subtle btn-compact" data-onb="skip">Skip</button>' +
        '<button type="button" class="btn btn-primary btn-compact" data-onb="next">' +
        (i === steps.length - 1 ? "Got it" : "Next") + "</button>" +
        "</div></div>";

      // Position the popover: below the target if room, else above.
      var top = r.bottom + 12;
      if (top + 160 > window.innerHeight) top = Math.max(12, r.top - 172);
      var left = Math.min(Math.max(12, r.left), window.innerWidth - 320);
      pop.style.top = top + "px";
      pop.style.left = left + "px";

      pop.querySelector('[data-onb="next"]').focus();
      pop.querySelector('[data-onb="next"]').onclick = next;
      pop.querySelector('[data-onb="skip"]').onclick = finish;
    }

    function next() {
      i += 1;
      if (i >= steps.length) { finish(); return; }
      render();
    }

    render();
    window.addEventListener("resize", render, { passive: true });
  }

  function showWelcome() {
    var steps = STEPS.filter(function (s) { return isVisible(document.querySelector(s.sel)); });

    var modal = build("div", "onb-welcome-backdrop");
    var card = build("div", "onb-welcome-card",
      '<span class="onb-kicker">Welcome</span>' +
      "<h2>Keep the Upper Cumberland clean</h2>" +
      "<p>Report litter you spot, join cleanups, and watch the map fill up with real community impact.</p>" +
      '<div class="onb-welcome-actions">' +
      (steps.length ? '<button type="button" class="btn btn-primary" data-onb="tour">Take a quick tour</button>' : "") +
      '<button type="button" class="btn btn-subtle" data-onb="dismiss">' +
      (steps.length ? "Skip" : "Got it") + "</button>" +
      "</div>");
    card.setAttribute("role", "dialog");
    card.setAttribute("aria-modal", "true");
    card.setAttribute("aria-label", "Welcome to UC CleanUp");
    modal.appendChild(card);
    document.body.appendChild(modal);

    function close() {
      try { localStorage.setItem(KEY, "1"); } catch (e) {}
      modal.remove();
    }
    var tourBtn = card.querySelector('[data-onb="tour"]');
    card.querySelector('[data-onb="dismiss"]').onclick = close;
    if (tourBtn) {
      tourBtn.focus();
      tourBtn.onclick = function () { modal.remove(); runTour(steps); };
    } else {
      card.querySelector('[data-onb="dismiss"]').focus();
    }
    modal.addEventListener("keydown", function (e) { if (e.key === "Escape") close(); });
  }

  // Public: replay the tour on demand (ignores the "seen" flag).
  window.ucStartTour = function () {
    var steps = STEPS.filter(function (s) { return isVisible(document.querySelector(s.sel)); });
    if (steps.length) runTour(steps);
    else showWelcome();
  };

  function init() {
    if (!document.getElementById("map")) return; // map page only
    var seen;
    try { seen = localStorage.getItem(KEY); } catch (e) { seen = "1"; }
    if (seen) return;
    // Give the map a moment to render its controls before measuring.
    setTimeout(showWelcome, 900);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
