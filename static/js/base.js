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
    var settingsCountyGrid = document.getElementById("settings-county-grid");
    var settingsCountyAll = document.getElementById("settings-county-all");
    var settingsDistrictList = document.getElementById("settings-district-list");
    var saveLabelEl = settingsForm ? settingsForm.querySelector(".btn-label") : null;
    var saveSpinner = settingsForm ? settingsForm.querySelector(".loading-spinner") : null;
    if (!settingsBtn) return;

    // County Select All / Deselect All
    if (settingsCountyAll && settingsCountyGrid) {
      function updateCountySelectAll() {
        var boxes = settingsCountyGrid.querySelectorAll("input[name='default_counties']");
        var checkedCount = Array.from(boxes).filter(function (b) { return b.checked; }).length;
        var all = checkedCount === boxes.length;
        var none = checkedCount === 0;
        settingsCountyAll.checked = all;
        settingsCountyAll.indeterminate = !all && !none;
        var span = settingsCountyAll.closest("label").querySelector("span");
        if (span) span.textContent = all ? "Deselect All" : "Select All";
      }
      settingsCountyAll.addEventListener("change", function (e) {
        var checked = e.target.checked;
        e.target.indeterminate = false;
        settingsCountyGrid.querySelectorAll("input[name='default_counties']").forEach(function (chk) {
          chk.checked = checked;
        });
        var span = settingsCountyAll.closest("label").querySelector("span");
        if (span) span.textContent = checked ? "Deselect All" : "Select All";
      });
      settingsCountyGrid.querySelectorAll("input[name='default_counties']").forEach(function (chk) {
        chk.addEventListener("change", updateCountySelectAll);
      });
    }

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
      var initialAllChecked = allChecked || (checkedSlugs && checkedSlugs.length === districts.length);
      settingsDistrictList.innerHTML = "";

      // --- Select All / Deselect All row ---
      var selectAllLabel = document.createElement("label");
      selectAllLabel.className = "layer-toggle layer-toggle--all";
      selectAllLabel.innerHTML =
        '<input type="checkbox"' + (initialAllChecked ? " checked" : "") + ">" +
        "<span>" + (initialAllChecked ? "Deselect All" : "Select All") + "</span>";
      settingsDistrictList.appendChild(selectAllLabel);

      var divider = document.createElement("div");
      divider.className = "layer-toggle-divider";
      settingsDistrictList.appendChild(divider);

      // --- 2-column district grid ---
      var grid = document.createElement("div");
      grid.className = "settings-district-grid";
      settingsDistrictList.appendChild(grid);

      var selectAllChk = selectAllLabel.querySelector("input");
      var selectAllSpan = selectAllLabel.querySelector("span");

      function updateSelectAll() {
        var boxes = grid.querySelectorAll("input[name='district_slugs']");
        var checkedCount = Array.from(boxes).filter(function (b) { return b.checked; }).length;
        var all = checkedCount === boxes.length;
        var none = checkedCount === 0;
        selectAllChk.checked = all;
        selectAllChk.indeterminate = !all && !none;
        selectAllSpan.textContent = all ? "Deselect All" : "Select All";
      }

      // Render each district into the grid
      districts.forEach(function (d) {
        var checked = allChecked || (checkedSlugs && checkedSlugs.indexOf(d.slug) !== -1);
        var label = document.createElement("label");
        label.className = "layer-toggle";
        label.innerHTML =
          '<input type="checkbox" name="district_slugs" value="' + d.slug + '"' + (checked ? " checked" : "") + ">" +
          "<span>" + d.name + "</span>";
        label.querySelector("input").addEventListener("change", function (e) {
          if (window.mapDistrictToggle) window.mapDistrictToggle(d.slug, e.target.checked);
          updateSelectAll();
        });
        grid.appendChild(label);
      });

      // Select All / Deselect All handler
      selectAllChk.addEventListener("change", function (e) {
        var checked = e.target.checked;
        e.target.indeterminate = false;
        grid.querySelectorAll("input[name='district_slugs']").forEach(function (chk) {
          if (chk.checked !== checked) {
            chk.checked = checked;
            if (window.mapDistrictToggle) window.mapDistrictToggle(chk.value, checked);
          }
        });
        selectAllSpan.textContent = checked ? "Deselect All" : "Select All";
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
            // Restore saved default counties
            var savedCounties = prefs.default_counties || [];
            if (settingsCountyGrid && savedCounties.length) {
              settingsCountyGrid.querySelectorAll("input[name='default_counties']").forEach(function (chk) {
                chk.checked = savedCounties.indexOf(chk.value) !== -1;
              });
              if (settingsCountyAll) {
                var allBoxes = settingsCountyGrid.querySelectorAll("input[name='default_counties']");
                var checkedCount = Array.from(allBoxes).filter(function (b) { return b.checked; }).length;
                var allChecked = checkedCount === allBoxes.length;
                settingsCountyAll.checked = allChecked;
                settingsCountyAll.indeterminate = !allChecked && checkedCount > 0;
                var span = settingsCountyAll.closest("label").querySelector("span");
                if (span) span.textContent = allChecked ? "Deselect All" : "Select All";
              }
            }
            // Restore saved visible districts
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

    settingsBtn.addEventListener("click", function (e) {
      e.stopPropagation();
      // Close hamburger dropdown before opening modal
      var hamburgerEl = document.getElementById("hamburger-btn");
      var navCollapseEl = document.getElementById("nav-collapse");
      if (hamburgerEl) hamburgerEl.setAttribute("aria-expanded", "false");
      if (navCollapseEl) navCollapseEl.classList.remove("is-open");
      // Reset and open modal
      if (settingsDistrictList) settingsDistrictList.innerHTML = '<span class="settings-loading">Loading\u2026</span>';
      setSettingsStatus("");
      U.openModal("settings-modal");
      loadSettingsData();
    });

    if (settingsForm && prefEndpoint) {
      settingsForm.addEventListener("submit", function (e) {
        e.preventDefault();

        // Collect checked county values
        var countyBoxes = settingsCountyGrid
          ? Array.from(settingsCountyGrid.querySelectorAll("input[name='default_counties']"))
          : [];
        var checkedCounties = countyBoxes.filter(function (b) { return b.checked; }).map(function (b) { return b.value; });
        // Empty array = no preference saved (use app default)
        var countiesToSave = checkedCounties.length === countyBoxes.length ? [] : checkedCounties;

        // Collect visible district slugs
        var distBoxes = settingsDistrictList
          ? Array.from(settingsDistrictList.querySelectorAll("input[name='district_slugs']"))
          : [];
        var checkedSlugs = distBoxes.filter(function (b) { return b.checked; }).map(function (b) { return b.value; });
        var slugsToSave = checkedSlugs.length === distBoxes.length ? [] : checkedSlugs;

        if (saveLabelEl) saveLabelEl.textContent = "Saving\u2026";
        if (saveSpinner) saveSpinner.classList.remove("hidden");

        U.fetchJson(prefEndpoint, {
          method: "POST",
          headers: { "X-CSRFToken": U.getCsrfToken(), "Content-Type": "application/json" },
          body: JSON.stringify({ default_counties: countiesToSave, visible_district_slugs: slugsToSave }),
        }).then(function () {
          setSettingsStatus("Preferences saved.", "success");
          // Immediately update the map to reflect the chosen counties (don't wait for reload).
          // Use checkedCounties (actual selection) not countiesToSave, because countiesToSave
          // is [] when all counties are checked (backend meaning: "no preference").
          if (checkedCounties.length && window.mapApplyCounties) {
            window.mapApplyCounties(checkedCounties);
          }
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
