(function () {
  "use strict";
  var U = window.AppUtils;
  var config = window.APP_BASE_CONFIG || {};

  /* ---- Feedback modal ---- */
  var feedbackOpenBtn = document.getElementById("feedback-open-btn");
  var feedbackForm = document.getElementById("feedback-form");
  var feedbackStatus = document.getElementById("feedback-status");
  var feedbackPageUrl = document.getElementById("feedback-page-url");

  function setStatus(message, state) {
    if (!feedbackStatus) return;
    feedbackStatus.textContent = message || "";
    feedbackStatus.classList.remove("is-error", "is-success");
    if (state) feedbackStatus.classList.add(state);
  }

  if (feedbackOpenBtn) {
    feedbackOpenBtn.addEventListener("click", function () {
      if (feedbackPageUrl) feedbackPageUrl.value = window.location.pathname + window.location.search;
      U.openModal("feedback-modal");
    });
  }

  if (feedbackForm) {
    feedbackForm.addEventListener("submit", function (e) {
      e.preventDefault();
      setStatus("");
      U.fetchJson(config.endpoints.feedbackCreate, {
        method: "POST",
        headers: { "X-CSRFToken": U.getCsrfToken() },
        body: new FormData(feedbackForm),
      }).then(function () {
        feedbackForm.reset();
        if (feedbackPageUrl) feedbackPageUrl.value = window.location.pathname + window.location.search;
        setStatus("Feedback sent. Thank you.", "is-success");
        setTimeout(function () { U.closeModal("feedback-modal"); }, 900);
      }).catch(function (err) {
        setStatus(err.message || "Unable to send feedback.", "is-error");
      });
    });
  }

  /* ---- Settings modal ---- */
  (function () {
    var settingsBtn = document.getElementById("settings-open-btn");
    var settingsForm = document.getElementById("settings-form");
    var settingsStatus = document.getElementById("settings-status");
    var settingsCounty = document.getElementById("settings-county");
    var settingsDistrictList = document.getElementById("settings-district-list");
    var saveLabelEl = settingsForm ? settingsForm.querySelector(".btn-label") : null;
    var saveSpinner = settingsForm ? settingsForm.querySelector(".loading-spinner") : null;
    if (!settingsBtn) return;

    var prefEndpoint = (config.endpoints || {}).preferences;
    var districtEndpoint = (config.endpoints || {}).districts;

    function setSettingsStatus(msg, state) {
      if (!settingsStatus) return;
      settingsStatus.textContent = msg || "";
      settingsStatus.className = "feedback-status" + (state ? " is-" + state : "");
    }

    function renderDistrictCheckboxes(districts, checkedSlugs) {
      if (!settingsDistrictList) return;
      var allChecked = !checkedSlugs || !checkedSlugs.length;
      settingsDistrictList.innerHTML = "";
      districts.forEach(function (d) {
        var checked = allChecked || checkedSlugs.indexOf(d.slug) !== -1;
        var label = document.createElement("label");
        label.className = "layer-toggle";
        label.innerHTML =
          '<input type="checkbox" name="district_slugs" value="' + d.slug + '"' + (checked ? " checked" : "") + ">" +
          "<span>" + d.name + "</span>";
        label.querySelector("input").addEventListener("change", function (e) {
          // Real-time layer toggle on the map page if available
          if (window.mapDistrictToggle) window.mapDistrictToggle(d.slug, e.target.checked);
        });
        settingsDistrictList.appendChild(label);
      });
    }

    function loadSettingsData() {
      if (!districtEndpoint) return;
      U.fetchJson(districtEndpoint).then(function (data) {
        var districts = (data.districts || []).filter(function (d) {
          return d.slug !== "putnam-county";
        }).sort(function (a, b) {
          var na = parseInt(a.name.replace(/\D/g, ""), 10) || 0;
          var nb = parseInt(b.name.replace(/\D/g, ""), 10) || 0;
          return na - nb;
        });

        // Render with all checked initially
        renderDistrictCheckboxes(districts, []);

        // Then overlay saved prefs if authenticated
        if (config.isAuthenticated && prefEndpoint) {
          U.fetchJson(prefEndpoint).then(function (prefs) {
            if (settingsCounty && prefs.default_county) {
              settingsCounty.value = prefs.default_county;
            }
            var slugs = prefs.visible_district_slugs || [];
            if (slugs.length) {
              renderDistrictCheckboxes(districts, slugs);
            }
          }).catch(function () {});
        }
      }).catch(function () {
        if (settingsDistrictList) {
          settingsDistrictList.innerHTML = '<span style="color:var(--color-text-muted)">Unable to load districts.</span>';
        }
      });
    }

    settingsBtn.addEventListener("click", function () {
      if (settingsCounty) settingsCounty.value = "";
      if (settingsDistrictList) settingsDistrictList.innerHTML = '<span class="settings-loading">Loading\u2026</span>';
      setSettingsStatus("");
      U.openModal("settings-modal");
      loadSettingsData();
    });

    if (settingsForm && prefEndpoint) {
      settingsForm.addEventListener("submit", function (e) {
        e.preventDefault();
        var county = settingsCounty ? settingsCounty.value : "";
        var boxes = settingsDistrictList
          ? Array.from(settingsDistrictList.querySelectorAll("input[name='district_slugs']"))
          : [];
        var checked = boxes.filter(function (b) { return b.checked; }).map(function (b) { return b.value; });
        // Empty array = all visible (default)
        var slugsToSave = checked.length === boxes.length ? [] : checked;

        if (saveLabelEl) saveLabelEl.textContent = "Saving\u2026";
        if (saveSpinner) saveSpinner.classList.remove("hidden");

        U.fetchJson(prefEndpoint, {
          method: "POST",
          headers: { "X-CSRFToken": U.getCsrfToken(), "Content-Type": "application/json" },
          body: JSON.stringify({ default_county: county, visible_district_slugs: slugsToSave }),
        }).then(function () {
          setSettingsStatus("Preferences saved.", "success");
          setTimeout(function () { U.closeModal("settings-modal"); }, 700);
        }).catch(function (err) {
          setSettingsStatus(err.message || "Failed to save.", "error");
        }).finally(function () {
          if (saveLabelEl) saveLabelEl.textContent = "Save Preferences";
          if (saveSpinner) saveSpinner.classList.add("hidden");
        });
      });
    }
  }());

  /* ---- Generic close-modal buttons ---- */
  document.querySelectorAll("[data-close-modal]").forEach(function (btn) {
    btn.addEventListener("click", function () {
      U.closeModal(btn.getAttribute("data-close-modal"));
    });
  });

  /* ---- Hamburger toggle ---- */
  var hamburger = document.getElementById("hamburger-btn");
  var navCollapse = document.getElementById("nav-collapse");
  if (hamburger && navCollapse) {
    hamburger.addEventListener("click", function (e) {
      e.stopPropagation();
      var open = hamburger.getAttribute("aria-expanded") === "true";
      hamburger.setAttribute("aria-expanded", String(!open));
      navCollapse.classList.toggle("is-open", !open);
    });
    navCollapse.addEventListener("click", function (e) {
      e.stopPropagation();
    });
    document.addEventListener("click", function () {
      hamburger.setAttribute("aria-expanded", "false");
      navCollapse.classList.remove("is-open");
    });
  }
})();
