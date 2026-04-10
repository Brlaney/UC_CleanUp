(function () {
  "use strict";
  var U = window.AppUtils;
  var config = window.APP_CONFIG || {};
  var isAuth = config.isAuthenticated;

  /* ---- CSS colour helpers ---- */
  function cssVar(name, fallback) {
    return getComputedStyle(document.documentElement).getPropertyValue(name).trim() || fallback;
  }

  var COLORS = {
    pending: cssVar("--map-marker-pending", "#db5a26"),
    in_progress: cssVar("--map-marker-in-progress", "#ccb10f"),
    cleaned: cssVar("--map-marker-cleaned", "#1f944f"),
    district: cssVar("--color-district-accent", "#0e5ea8"),
    districtFill: cssVar("--map-county-boundary-fill", "rgba(14,94,168,0.1)"),
    maskColor: cssVar("--map-outside-mask-color", "#081421"),
    maskOpacity: parseFloat(cssVar("--map-outside-mask-opacity", "0.58")),
    route: cssVar("--map-route-draw-color", "#2474cc"),
  };

  function statusColor(s) {
    return COLORS[(s || "").toLowerCase().replace(/ /g, "_")] || COLORS.pending;
  }

  /* ---- Leaflet map init ---- */
  var map = L.map("map", {
    center: [36.1627, -85.5016],
    zoom: 12,
    zoomSnap: 0.25,
    zoomDelta: 0.5,
    wheelDebounceTime: 80,
    zoomControl: false,
  });
  L.control.zoom({ position: "topleft" }).addTo(map);
  L.tileLayer("https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}.png", {
    maxZoom: 20,
    tileSize: 256,
    detectRetina: false,
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors &copy; <a href="https://carto.com/">CARTO</a>',
    subdomains: "abcd",
  }).addTo(map);

  var trashLayer = L.layerGroup().addTo(map);
  var areaLayer = L.layerGroup().addTo(map);
  var districtPane = map.createPane("districtPane");
  districtPane.style.zIndex = 350;
  var maskPane = map.createPane("maskPane");
  maskPane.style.zIndex = 340;

  var districtBoundaryLayer = null;
  var outsideMaskLayer = null;

  /* ---- State ---- */
  var currentMode = "report"; // "report" | "cleanup"
  var reportSubMode = null;   // null | "pin" | "area"
  var pendingMarker = null;
  var drawControl = null;

  /* ---- DOM refs ---- */
  var modeReportBtn = document.getElementById("mode-report-btn");
  var modeCleanupBtn = document.getElementById("mode-cleanup-btn");
  var reportPanel = document.getElementById("report-mode-panel");
  var cleanupPanel = document.getElementById("cleanup-mode-panel");
  var placePinBtn = document.getElementById("place-pin-btn");
  var drawAreaBtn = document.getElementById("draw-area-btn");
  var applyFiltersBtn = document.getElementById("apply-filters-btn");
  var detailContent = document.getElementById("detail-content");
  var trashForm = document.getElementById("trash-form");
  var cleanedForm = document.getElementById("cleaned-form");

  /* Mobile DOM refs */
  var mobileDetailCard = document.getElementById("mobile-detail-card");
  var mobileDetailBody = document.getElementById("mobile-detail-body");
  var mobileDetailClose = document.getElementById("mobile-detail-close");
  var mobileLayersCard = document.getElementById("mobile-layers-card");
  var mobileLayersClose = document.getElementById("mobile-layers-close");
  var mobileModePicker = document.getElementById("mobile-mode-picker");
  var fabMode = document.getElementById("fab-mode");
  var fabLayers = document.getElementById("fab-layers");

  function isMobileView() { return window.innerWidth <= 768; }

  /* ---- Mobile FAB controls ---- */
  (function () {
    if (!fabLayers || !fabMode) return;

    // Resolve icon URLs from the picker img elements (always present in DOM)
    var MODE_ICONS = {};
    document.querySelectorAll("[data-pick-mode]").forEach(function (btn) {
      var img = btn.querySelector("img");
      if (img) MODE_ICONS[btn.dataset.pickMode] = img.src;
    });

    var mobileMode = "pin"; // pin | polygon | cleanup

    function setMobileMode(mode) {
      mobileMode = mode;
      // Update FAB background image
      if (fabMode && MODE_ICONS[mode]) fabMode.style.backgroundImage = "url(" + MODE_ICONS[mode] + ")";
      // Highlight active pick btn
      document.querySelectorAll("[data-pick-mode]").forEach(function (btn) {
        btn.classList.toggle("is-active", btn.dataset.pickMode === mode);
      });
      // Drive the underlying mode system
      if (mode === "cleanup") {
        setMode("cleanup");
      } else {
        setMode("report");
        if (mode === "pin") {
          cancelReportSubMode();
          reportSubMode = "pin";
          map.getContainer().style.cursor = "crosshair";
          U.announce("Tap the map to place a pin.");
        } else if (mode === "polygon") {
          cancelReportSubMode();
          reportSubMode = "area";
          drawControl = new L.Draw.Polygon(map, {
            shapeOptions: { color: COLORS.route, weight: 3, fillOpacity: 0.15 },
          });
          drawControl.enable();
          U.announce("Draw a polygon on the map.");
        }
      }
      mobileModePicker.classList.add("hidden");
    }

    // Layers FAB
    fabLayers.addEventListener("click", function (e) {
      e.stopPropagation();
      mobileLayersCard.classList.toggle("hidden");
      mobileModePicker.classList.add("hidden");
    });
    if (mobileLayersClose) {
      mobileLayersClose.addEventListener("click", function () {
        mobileLayersCard.classList.add("hidden");
      });
    }

    // Mobile layer checkbox syncs with desktop checkbox
    var mobLayerChk = document.getElementById("layer-district3-mob");
    var deskLayerChk = document.getElementById("layer-district3");
    if (mobLayerChk && deskLayerChk) {
      mobLayerChk.addEventListener("change", function () {
        deskLayerChk.checked = mobLayerChk.checked;
        deskLayerChk.dispatchEvent(new Event("change"));
      });
    }

    // Mode FAB — tap opens/closes picker
    fabMode.addEventListener("click", function (e) {
      e.stopPropagation();
      mobileModePicker.classList.toggle("hidden");
      mobileLayersCard.classList.add("hidden");
    });

    // Pick a mode from the picker
    document.querySelectorAll("[data-pick-mode]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        if (!requireAuth()) return;
        setMobileMode(btn.dataset.pickMode);
      });
    });

    // Close cards when tapping the map
    map.on("click", function () {
      if (!isMobileView()) return;
      mobileLayersCard.classList.add("hidden");
      mobileModePicker.classList.add("hidden");
    });

    // Mobile detail card close
    if (mobileDetailClose) {
      mobileDetailClose.addEventListener("click", function () {
        mobileDetailCard.classList.add("hidden");
      });
    }

    // Photo lightbox delegation for mobile detail body
    if (mobileDetailBody) {
      mobileDetailBody.addEventListener("click", function (e) {
        var img = e.target.closest("img");
        if (img) {
          var lb = document.getElementById("photo-lightbox");
          var lbImg = document.getElementById("photo-lightbox-img");
          if (lb && lbImg) {
            lbImg.src = img.src;
            lbImg.alt = img.alt || "";
            lb.classList.remove("hidden");
            document.body.style.overflow = "hidden";
          }
        }
      });
    }
  }());

  /* ---- Photo lightbox ---- */
  (function () {
    var lightbox = document.getElementById("photo-lightbox");
    var lightboxImg = document.getElementById("photo-lightbox-img");
    var closeBtn = document.getElementById("photo-lightbox-close");
    if (!lightbox || !lightboxImg) return;

    function openLightbox(src, alt) {
      lightboxImg.src = src;
      lightboxImg.alt = alt || "";
      lightbox.classList.remove("hidden");
      document.body.style.overflow = "hidden";
    }

    function closeLightbox() {
      lightbox.classList.add("hidden");
      lightboxImg.src = "";
      document.body.style.overflow = "";
    }

    // Event delegation — works for dynamically injected imgs
    document.getElementById("detail-content").addEventListener("click", function (e) {
      var img = e.target.closest("img");
      if (img) openLightbox(img.src, img.alt);
    });

    closeBtn.addEventListener("click", closeLightbox);
    lightbox.addEventListener("click", function (e) {
      if (e.target === lightbox) closeLightbox();
    });
    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape") closeLightbox();
    });
  }());

  /* ---- Helpers ---- */
  function getBBox() {
    var b = map.getBounds();
    return b.getWest() + "," + b.getSouth() + "," + b.getEast() + "," + b.getNorth();
  }

  function titleCase(s) {
    return (s || "").replace(/_/g, " ").replace(/\b\w/g, function (c) { return c.toUpperCase(); });
  }

  function tokenClass(s) {
    return (s || "").toLowerCase().replace(/_/g, "-");
  }

  function formatDate(iso) {
    if (!iso) return "-";
    const d = new Date(iso);
    const date = d.toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });
    const time = d.toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit", hour12: true });
    return date + ", " + time;
  }

  function setDetail(html) {
    if (detailContent) detailContent.innerHTML = html;
  }

  function setLoading(btnId, loading) {
    var btn = document.getElementById(btnId);
    if (!btn) return;
    var spinner = btn.querySelector(".loading-spinner");
    var label = btn.querySelector(".btn-label");
    if (loading) {
      btn.disabled = true;
      if (spinner) spinner.classList.remove("hidden");
      if (label) label.textContent = "Submitting\u2026";
    } else {
      btn.disabled = false;
      if (spinner) spinner.classList.add("hidden");
    }
  }

  function requireAuth() {
    if (isAuth) return true;
    U.openModal("auth-gate");
    return false;
  }

  /* ---- District boundary loading ---- */
  var WORLD_RING = [
    [-90, -180], [90, -180], [90, 180], [-90, 180], [-90, -180],
  ];

  // Map of slug → Leaflet layer, populated after loadDistricts()
  var districtLayers = {};

  function loadDistricts() {
    U.fetchJson(config.endpoints.districts).then(function (data) {
      var districts = data.districts || [];
      if (!districts.length) return;

      var county = null;
      var innerDistricts = [];
      districts.forEach(function (d) {
        if (d.slug === "putnam-county") { county = d; }
        else { innerDistricts.push(d); }
      });
      if (!county && districts.length) county = districts[0];

      // Outside mask from county boundary
      if (county) {
        var geom = county.geometry;
        var holes = [];
        if (geom.type === "MultiPolygon") {
          geom.coordinates.forEach(function (poly) {
            holes.push(poly[0].map(function (c) { return [c[1], c[0]]; }));
          });
        } else if (geom.type === "Polygon") {
          holes.push(geom.coordinates[0].map(function (c) { return [c[1], c[0]]; }));
        }
        outsideMaskLayer = L.polygon(
          [WORLD_RING.map(function (c) { return [c[0], c[1]]; })].concat(holes),
          { pane: "maskPane", color: "transparent", fillColor: COLORS.maskColor, fillOpacity: COLORS.maskOpacity, interactive: false }
        ).addTo(map);

        var countyLayer = L.geoJSON(geom, {
          pane: "districtPane", interactive: false,
          style: { color: COLORS.district, weight: 2, fillOpacity: 0, dashArray: "6 4" },
        }).addTo(map);
        map.fitBounds(countyLayer.getBounds(), { padding: [30, 30] });
      }

      // Sort inner districts numerically by name ("District 1", "District 2", …)
      innerDistricts.sort(function (a, b) {
        var na = parseInt(a.name.replace(/\D/g, ""), 10) || 0;
        var nb = parseInt(b.name.replace(/\D/g, ""), 10) || 0;
        return na - nb;
      });

      // Render each district boundary + build layer toggle checkboxes
      var desktopContainer = document.getElementById("layer-toggles");
      var mobileContainer  = document.getElementById("layer-toggles-mob");

      innerDistricts.forEach(function (d) {
        var layer = L.geoJSON(d.geometry, {
          pane: "districtPane",
          style: { color: COLORS.district, weight: 2.5, fillColor: COLORS.districtFill, fillOpacity: 0.10 },
        });
        layer.bindTooltip(d.name, { permanent: false, direction: "center", className: "district-label" });
        layer.addTo(map);
        districtLayers[d.slug] = layer;

        // Build a checkbox label for desktop and mobile
        [desktopContainer, mobileContainer].forEach(function (container) {
          if (!container) return;
          var id = "layer-chk-" + d.slug + (container === mobileContainer ? "-mob" : "");
          var label = document.createElement("label");
          label.className = "layer-toggle";
          label.innerHTML =
            '<input type="checkbox" id="' + id + '" checked data-district-slug="' + d.slug + '">' +
            '<span>' + d.name + '</span>';
          container.appendChild(label);

          label.querySelector("input").addEventListener("change", function (e) {
            var targetLayer = districtLayers[d.slug];
            if (!targetLayer) return;
            if (e.target.checked) { targetLayer.addTo(map); }
            else { targetLayer.remove(); }
            // Keep the paired checkbox in sync
            var pairedId = container === mobileContainer
              ? "layer-chk-" + d.slug
              : "layer-chk-" + d.slug + "-mob";
            var paired = document.getElementById(pairedId);
            if (paired) paired.checked = e.target.checked;
          });
        });
      });

    }).catch(function () {
      // Districts may not be seeded yet; fail silently
    });
  }

  /* ---- Feature loading ---- */
  function getStatusFilters() {
    var checks = document.querySelectorAll('input[name="status"]:checked');
    return Array.from(checks).map(function (c) { return c.value; }).join(",");
  }

  function loadFeatures() {
    var url = config.endpoints.features + "?bbox=" + getBBox();
    var statuses = getStatusFilters();
    if (statuses) url += "&status=" + statuses;

    U.fetchJson(url).then(function (data) {
      trashLayer.clearLayers();
      areaLayer.clearLayers();
      var features = data.features || [];

      features.forEach(function (f) {
        var p = f.properties;
        var coords = f.geometry.coordinates;
        var marker = L.circleMarker([coords[1], coords[0]], {
          radius: 8,
          fillColor: statusColor(p.status),
          color: "#fff",
          weight: 2,
          fillOpacity: 0.9,
        });

        var popup = '<div class="map-popup">' +
          '<strong>' + U.escapeHtml(p.title || "Trash Site") + '</strong>' +
          '<span class="popup-status popup-status--' + tokenClass(p.status) + '">' + titleCase(p.status) + '</span>';
        if (p.can_mark_cleaned && p.status !== "CLEANED") {
          popup += '<button class="btn btn-secondary btn-compact popup-clean-btn" ' +
            'data-mark-cleaned="' + p.id + '">Mark Cleaned</button>';
        }
        popup += '</div>';
        marker.bindPopup(popup);

        marker.on("click", function () {
          showDetail(p.id);
        });

        marker.addTo(trashLayer);

        // Render area polygon if present
        if (p.area_geojson) {
          L.geoJSON(p.area_geojson, {
            style: {
              color: statusColor(p.status),
              weight: 2,
              fillColor: statusColor(p.status),
              fillOpacity: 0.15,
              dashArray: "5 5",
            },
            interactive: false,
          }).addTo(areaLayer);
        }
      });

      U.announce(features.length + " report" + (features.length !== 1 ? "s" : "") + " loaded.");
    }).catch(function () {
      U.showToast("Failed to load map features.", "error");
    });
  }

  /* ---- Detail panel ---- */
  function renderBadge(label, cls) {
    return '<span class="detail-badge detail-badge--' + cls + '">' + U.escapeHtml(label) + '</span>';
  }

  function renderMeta(label, value) {
    return '<div class="detail-meta-item"><dt>' + U.escapeHtml(label) + '</dt><dd>' + U.escapeHtml(value) + '</dd></div>';
  }

  function showDetail(siteId) {
    var mobile = isMobileView();
    if (mobile) {
      mobileDetailBody.innerHTML = '<p style="color:var(--color-text-muted)">Loading\u2026</p>';
      mobileDetailCard.classList.remove("hidden");
    } else {
      setDetail('<p style="color:var(--color-text-muted)">Loading\u2026</p>');
    }
    var url = config.endpoints.trashUpdateBase + siteId + "/detail/";
    U.fetchJson(url).then(function (site) {
      var html = '<div class="detail-panel">';
      html += '<div class="detail-panel-header">';
      html += '<span class="detail-kicker">Trash Site</span>';
      html += '<h3>' + U.escapeHtml(site.title || "Unnamed Site") + '</h3>';
      html += '<div class="detail-badge-row">';
      html += renderBadge(titleCase(site.status), tokenClass(site.status));
      if (site.severity) html += renderBadge(titleCase(site.severity), tokenClass(site.severity));
      if (site.hazard_flag) html += renderBadge("Hazard", "hazard");
      html += '</div></div>';

      html += '<dl class="detail-meta-grid">';
      html += renderMeta("Reported by", site.created_by);
      html += renderMeta("Created", formatDate(site.created_at));
      if (site.cleaned_at) html += renderMeta("Cleaned", formatDate(site.cleaned_at));
      html += '</dl>';

      if (site.description) {
        html += '<div class="detail-section"><h4>Description</h4>';
        html += '<p class="detail-copy">' + U.escapeHtml(site.description) + '</p></div>';
      }

      // Photos by type
      var photos = site.photos || {};
      ["report", "before", "after"].forEach(function (type) {
        var urls = photos[type] || [];
        if (urls.length) {
          html += '<div class="detail-section"><h4>' + titleCase(type) + ' Photos</h4>';
          html += '<div class="proof-photo-grid">';
          urls.forEach(function (u) {
            html += '<img src="' + U.escapeHtml(u) + '" alt="' + type + ' photo">';
          });
          html += '</div></div>';
        }
      });

      // Proofs
      if (site.proofs && site.proofs.length) {
        html += '<div class="detail-section"><h4>Proof History</h4><div class="proof-list">';
        site.proofs.forEach(function (proof) {
          html += '<div class="proof-card">';
          html += '<div class="proof-card-top">';
          if (proof.bags_count) html += '<span class="proof-bags">' + proof.bags_count + ' bags</span>';
          html += '<span class="proof-meta">' + U.escapeHtml(proof.created_by) + ' &middot; ' + formatDate(proof.created_at) + '</span>';
          html += '</div>';
          if (proof.note) html += '<p class="proof-note">' + U.escapeHtml(proof.note) + '</p>';
          if (proof.photos && proof.photos.length) {
            html += '<div class="proof-photo-grid">';
            proof.photos.forEach(function (ph) {
              html += '<img src="' + U.escapeHtml(ph.url) + '" alt="' + (ph.type || "proof") + ' photo">';
            });
            html += '</div>';
          }
          html += '</div>';
        });
        html += '</div></div>';
      }

      // Mark cleaned button
      if (site.permissions && site.permissions.can_mark_cleaned && site.status !== "CLEANED") {
        html += '<div class="detail-action-row">';
        html += '<button class="btn btn-secondary" data-open-cleaned="' + site.id + '">Mark Cleaned</button>';
        html += '</div>';
      }

      html += '</div>';

      var cleanBtn;
      if (mobile) {
        mobileDetailBody.innerHTML = html;
        cleanBtn = mobileDetailBody.querySelector("[data-open-cleaned]");
        if (cleanBtn) {
          cleanBtn.addEventListener("click", function () {
            openCleanedModal(cleanBtn.getAttribute("data-open-cleaned"));
          });
        }
      } else {
        setDetail(html);
        cleanBtn = detailContent.querySelector("[data-open-cleaned]");
        if (cleanBtn) {
          cleanBtn.addEventListener("click", function () {
            openCleanedModal(cleanBtn.getAttribute("data-open-cleaned"));
          });
        }
      }
    }).catch(function () {
      if (mobile) {
        mobileDetailBody.innerHTML = '<p style="color:var(--color-text-muted)">Unable to load details.</p>';
      } else {
        setDetail('<p style="color:var(--color-text-muted)">Unable to load details.</p>');
      }
    });
  }

  /* ---- Mode switching ---- */
  function setMode(mode) {
    currentMode = mode;
    cancelReportSubMode();

    modeReportBtn.classList.toggle("is-active", mode === "report");
    modeCleanupBtn.classList.toggle("is-active", mode === "cleanup");
    modeReportBtn.setAttribute("aria-pressed", mode === "report");
    modeCleanupBtn.setAttribute("aria-pressed", mode === "cleanup");

    reportPanel.classList.toggle("hidden", mode !== "report");
    cleanupPanel.classList.toggle("hidden", mode !== "cleanup");

    if (mode === "report") {
      U.announce("Report mode. Place a pin or draw an area on the map.");
    } else {
      U.announce("Cleanup mode. Click an existing report to start a cleanup.");
      loadFeatures();
    }
  }

  modeReportBtn.addEventListener("click", function () { setMode("report"); });
  modeCleanupBtn.addEventListener("click", function () { setMode("cleanup"); });

  /* ---- Report mode: pin placement ---- */
  function cancelReportSubMode() {
    reportSubMode = null;
    if (pendingMarker) { map.removeLayer(pendingMarker); pendingMarker = null; }
    if (drawControl) { drawControl.disable(); drawControl = null; }
    map.getContainer().style.cursor = "";
    if (placePinBtn) placePinBtn.classList.remove("is-active");
    if (drawAreaBtn) drawAreaBtn.classList.remove("is-active");
  }

  placePinBtn.addEventListener("click", function () {
    if (!requireAuth()) return;
    cancelReportSubMode();
    reportSubMode = "pin";
    placePinBtn.classList.add("is-active");
    map.getContainer().style.cursor = "crosshair";
    U.announce("Click on the map to place a pin for your report.");
  });

  drawAreaBtn.addEventListener("click", function () {
    if (!requireAuth()) return;
    cancelReportSubMode();
    reportSubMode = "area";
    drawAreaBtn.classList.add("is-active");
    drawControl = new L.Draw.Polygon(map, {
      shapeOptions: { color: COLORS.route, weight: 3, fillOpacity: 0.15 },
    });
    drawControl.enable();
    U.announce("Draw a polygon on the map to define the area.");
  });

  map.on("click", function (e) {
    if (currentMode !== "report" || reportSubMode !== "pin") return;
    if (!requireAuth()) return;

    if (pendingMarker) map.removeLayer(pendingMarker);
    pendingMarker = L.circleMarker(e.latlng, {
      radius: 10,
      fillColor: COLORS.pending,
      color: "#fff",
      weight: 3,
      fillOpacity: 0.9,
    }).addTo(map);

    var geojson = JSON.stringify({
      type: "Point",
      coordinates: [e.latlng.lng, e.latlng.lat],
    });
    document.getElementById("trash-geojson").value = geojson;
    U.openModal("trash-modal");
    cancelReportSubMode();
  });

  map.on(L.Draw.Event.CREATED, function (e) {
    if (currentMode !== "report" || reportSubMode !== "area") return;
    if (!requireAuth()) return;

    var layer = e.layer;
    var latlngs = layer.getLatLngs()[0];
    var coords = latlngs.map(function (ll) { return [ll.lng, ll.lat]; });
    coords.push(coords[0]); // close the ring

    var geojson = JSON.stringify({
      type: "Polygon",
      coordinates: [coords],
    });
    document.getElementById("trash-geojson").value = geojson;
    U.openModal("trash-modal");
    cancelReportSubMode();
  });

  /* ---- Report form submission ---- */
  trashForm.addEventListener("submit", function (e) {
    e.preventDefault();
    if (!requireAuth()) return;
    setLoading("trash-submit-btn", true);

    var formData = new FormData(trashForm);
    U.fetchJson(config.endpoints.trashCreate, {
      method: "POST",
      headers: { "X-CSRFToken": U.getCsrfToken() },
      body: formData,
    }).then(function () {
      trashForm.reset();
      document.getElementById("trash-photo-preview").innerHTML = "";
      U.closeModal("trash-modal");
      U.showToast("Trash report submitted!", "success");
      if (pendingMarker) { map.removeLayer(pendingMarker); pendingMarker = null; }
      loadFeatures();
    }).catch(function (err) {
      U.showToast(err.message || "Failed to submit report.", "error");
    }).finally(function () {
      setLoading("trash-submit-btn", false);
      var label = document.querySelector("#trash-submit-btn .btn-label");
      if (label) label.textContent = "Submit Report";
    });
  });

  /* ---- Cleanup mode: mark cleaned ---- */
  function openCleanedModal(siteId) {
    if (!requireAuth()) return;
    document.getElementById("cleaned-site-id").value = siteId;
    U.openModal("cleaned-modal");
  }

  cleanedForm.addEventListener("submit", function (e) {
    e.preventDefault();
    if (!requireAuth()) return;
    var siteId = document.getElementById("cleaned-site-id").value;
    if (!siteId) return;
    setLoading("cleaned-submit-btn", true);

    var formData = new FormData(cleanedForm);
    var url = config.endpoints.trashUpdateBase + siteId + "/mark-cleaned/";

    U.fetchJson(url, {
      method: "POST",
      headers: { "X-CSRFToken": U.getCsrfToken() },
      body: formData,
    }).then(function () {
      cleanedForm.reset();
      document.getElementById("before-photo-preview").innerHTML = "";
      document.getElementById("after-photo-preview").innerHTML = "";
      U.closeModal("cleaned-modal");
      U.showToast("Cleanup proof submitted!", "success");
      loadFeatures();
      showDetail(siteId);
    }).catch(function (err) {
      U.showToast(err.message || "Failed to submit cleanup.", "error");
    }).finally(function () {
      setLoading("cleaned-submit-btn", false);
      var label = document.querySelector("#cleaned-submit-btn .btn-label");
      if (label) label.textContent = "Submit Cleanup";
    });
  });

  /* ---- Popup event delegation for mark-cleaned ---- */
  map.on("popupopen", function (e) {
    var popup = e.popup.getElement();
    if (!popup) return;
    var btn = popup.querySelector("[data-mark-cleaned]");
    if (btn) {
      btn.addEventListener("click", function () {
        openCleanedModal(btn.getAttribute("data-mark-cleaned"));
        map.closePopup();
      });
    }
  });

  /* ---- Filter apply ---- */
  if (applyFiltersBtn) {
    applyFiltersBtn.addEventListener("click", function () {
      loadFeatures();
    });
  }

  /* ---- Reload on pan/zoom ---- */
  map.on("moveend", loadFeatures);

  /* ---- Photo previews ---- */
  U.setupPhotoPreview("trash-photos", "trash-photo-preview", 5);
  U.setupPhotoPreview("cleaned-before-photos", "before-photo-preview", 5);
  U.setupPhotoPreview("cleaned-after-photos", "after-photo-preview", 5);

  /* ---- Init ---- */
  setMode("report");
  loadDistricts();
  loadFeatures();

  // Deep link to a specific site from URL params
  var params = new URLSearchParams(window.location.search);
  var focusId = params.get("focus_id");
  if (focusId) {
    showDetail(focusId);
  }
})();
