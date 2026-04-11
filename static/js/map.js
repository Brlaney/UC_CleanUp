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

  var trashLayer = (typeof L.markerClusterGroup === "function"
    ? L.markerClusterGroup({ maxClusterRadius: 40, disableClusteringAtZoom: 14 })
    : L.layerGroup()
  ).addTo(map);
  var areaLayer = L.layerGroup().addTo(map);
  var eventLayer = L.layerGroup().addTo(map);
  var districtPane = map.createPane("districtPane");
  districtPane.style.zIndex = 350;
  var maskPane = map.createPane("maskPane");
  maskPane.style.zIndex = 340;
  var heatPane = map.createPane("heatPane");
  heatPane.style.zIndex = 320;

  var districtBoundaryLayer = null;
  var outsideMaskLayer = null;
  var heatLayer = null;
  var heatVisible = true;

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
  var createEventBtn = document.getElementById("create-event-btn");
  var detailContent = document.getElementById("detail-content");
  var trashForm = document.getElementById("trash-form");
  var cleanedForm = document.getElementById("cleaned-form");

  /* Mobile DOM refs */
  var mobileDetailCard = document.getElementById("mobile-detail-card");
  var mobileDetailBody = document.getElementById("mobile-detail-body");
  var mobileDetailClose = document.getElementById("mobile-detail-close");
  var mobileModePicker = document.getElementById("mobile-mode-picker");
  var fabMode = document.getElementById("fab-mode");

  function isMobileView() { return window.innerWidth <= 768; }

  /* ---- Mobile FAB controls ---- */
  (function () {
    if (!fabMode) return;

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

    // Mode FAB — tap opens/closes picker
    fabMode.addEventListener("click", function (e) {
      e.stopPropagation();
      mobileModePicker.classList.toggle("hidden");
    });

    // Pick a mode from the picker
    document.querySelectorAll("[data-pick-mode]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        if (!requireAuth()) return;
        setMobileMode(btn.dataset.pickMode);
      });
    });

    // Close picker when tapping the map
    map.on("click", function () {
      if (!isMobileView()) return;
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

  var UC_COUNTY_CENTROIDS = {
    "Cannon":     [35.8083940, -86.0624044],
    "Clay":       [36.5457493, -85.5457173],
    "Cumberland": [35.9523984, -84.9947614],
    "DeKalb":     [35.9822191, -85.8335959],
    "Fentress":   [36.3698921, -84.9377641],
    "Jackson":    [36.3542499, -85.6741278],
    "Macon":      [36.5377572, -86.0009596],
    "Overton":    [36.3448504, -85.2830756],
    "Pickett":    [36.5593638, -85.0757410],
    "Putnam":     [36.1409404, -85.4961801],
    "Smith":      [36.2566451, -85.9419149],
    "Van Buren":  [35.6992335, -85.4584092],
    "Warren":     [35.6782498, -85.7773428],
    "White":      [35.9270486, -85.4557854],
  };

  // Map of slug → Leaflet layer, populated after loadDistricts()
  var districtLayers = {};

  // Expose for settings modal real-time toggling
  window.mapDistrictToggle = function (slug, visible) {
    var layer = districtLayers[slug];
    if (!layer) return;
    if (visible) { layer.addTo(map); } else { layer.remove(); }
    var chk = document.getElementById("layer-chk-" + slug);
    if (chk) chk.checked = visible;
  };

  window.mapHeatToggle = function (visible) {
    heatVisible = visible;
    if (!heatLayer) return;
    if (visible) { heatLayer.addTo(map); } else { map.removeLayer(heatLayer); }
    var chk = document.getElementById("layer-chk-heatmap");
    if (chk) chk.checked = visible;
  };

  function syncSelectAll(container) {
    var allChk = container.querySelector("input[id^='layer-chk-all']");
    if (!allChk) return;
    var boxes = container.querySelectorAll("input[data-district-slug]");
    var checkedCount = Array.from(boxes).filter(function (b) { return b.checked; }).length;
    if (checkedCount === 0) {
      allChk.checked = false;
      allChk.indeterminate = false;
    } else if (checkedCount === boxes.length) {
      allChk.checked = true;
      allChk.indeterminate = false;
    } else {
      allChk.checked = false;
      allChk.indeterminate = true;
    }
  }

  function applyMapPreferences(prefs, knownDistricts) {
    var slugs = prefs.visible_district_slugs || [];
    if (slugs.length) {
      // Hide districts not in the saved list and uncheck their boxes
      var desktopContainer = document.getElementById("layer-toggles");
      knownDistricts.forEach(function (d) {
        if (slugs.indexOf(d.slug) === -1) {
          var layer = districtLayers[d.slug];
          if (layer) layer.remove();
          var chk = document.getElementById("layer-chk-" + d.slug);
          if (chk) chk.checked = false;
        }
      });
      if (desktopContainer) syncSelectAll(desktopContainer);

      // Fit the map to the combined bounds of the visible districts
      var combinedBounds = null;
      slugs.forEach(function (slug) {
        var layer = districtLayers[slug];
        if (!layer) return;
        var bounds = layer.getBounds();
        if (!bounds.isValid()) return;
        combinedBounds = combinedBounds ? combinedBounds.extend(bounds) : bounds;
      });
      if (combinedBounds && combinedBounds.isValid()) {
        map.fitBounds(combinedBounds, { padding: [50, 50] });
        return; // bounds already set — skip county centroid fallback
      }
    }

    // No specific districts saved (all visible) — fall back to county centroid
    var county = prefs.default_county;
    if (county && UC_COUNTY_CENTROIDS[county]) {
      map.setView(UC_COUNTY_CENTROIDS[county], 12);
    }
  }

  function loadDistricts() {
    // Use inlined data when available (eliminates 290 KB XHR from critical path).
    var inlined = config.districts;
    var promise = inlined
      ? Promise.resolve(inlined)
      : U.fetchJson(config.endpoints.districts);

    promise.then(function (data) {
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

      // Render each district boundary + build layer toggle checkboxes (desktop only)
      var desktopContainer = document.getElementById("layer-toggles");

      // "Select All" row
      if (desktopContainer) {
        var divider = document.createElement("div");
        divider.className = "layer-toggle-divider";
        var allLabel = document.createElement("label");
        allLabel.className = "layer-toggle layer-toggle--all";
        allLabel.innerHTML = '<input type="checkbox" id="layer-chk-all" checked><span>Select All</span>';
        desktopContainer.appendChild(allLabel);
        desktopContainer.appendChild(divider);

        allLabel.querySelector("input").addEventListener("change", function (e) {
          var checked = e.target.checked;
          e.target.indeterminate = false;
          innerDistricts.forEach(function (d) {
            var chk = document.getElementById("layer-chk-" + d.slug);
            if (chk) chk.checked = checked;
            var targetLayer = districtLayers[d.slug];
            if (!targetLayer) return;
            if (checked) { targetLayer.addTo(map); } else { targetLayer.remove(); }
          });
        });
      }

      innerDistricts.forEach(function (d) {
        var layer = L.geoJSON(d.geometry, {
          pane: "districtPane",
          interactive: false,
          style: { color: COLORS.district, weight: 2.5, fillColor: COLORS.districtFill, fillOpacity: 0.10 },
        });
        layer.bindTooltip(d.name, { permanent: false, direction: "center", className: "district-label" });
        layer.addTo(map);
        districtLayers[d.slug] = layer;

        // Desktop checkbox
        if (desktopContainer) {
          var id = "layer-chk-" + d.slug;
          var label = document.createElement("label");
          label.className = "layer-toggle";
          label.innerHTML =
            '<input type="checkbox" id="' + id + '" checked data-district-slug="' + d.slug + '">' +
            '<span>' + d.name + '</span>';
          desktopContainer.appendChild(label);

          label.querySelector("input").addEventListener("change", function (e) {
            var targetLayer = districtLayers[d.slug];
            if (!targetLayer) return;
            if (e.target.checked) { targetLayer.addTo(map); }
            else { targetLayer.remove(); }
            syncSelectAll(desktopContainer);
          });
        }
      });

      // Heatmap toggle (below districts)
      if (desktopContainer) {
        var heatDivEl = document.createElement("div");
        heatDivEl.className = "layer-toggle-divider";
        desktopContainer.appendChild(heatDivEl);
        var heatToggleLabel = document.createElement("label");
        heatToggleLabel.className = "layer-toggle";
        heatToggleLabel.innerHTML = '<input type="checkbox" id="layer-chk-heatmap" checked><span>Heat Map</span>';
        desktopContainer.appendChild(heatToggleLabel);
        heatToggleLabel.querySelector("input").addEventListener("change", function (e) {
          window.mapHeatToggle(e.target.checked);
        });
      }

      // Apply saved preferences (if authenticated)
      if (isAuth && config.endpoints && config.endpoints.preferences) {
        U.fetchJson(config.endpoints.preferences).then(function (prefs) {
          applyMapPreferences(prefs, innerDistricts);
        }).catch(function () {});
      }

    }).catch(function () {
      // Districts may not be seeded yet; fail silently
    });
  }

  /* ---- Heatmap ---- */
  function loadHeatmap() {
    if (!config.endpoints || !config.endpoints.heatmap) return;
    if (typeof L.heatLayer === "undefined") return;
    U.fetchJson(config.endpoints.heatmap).then(function (data) {
      var points = data.points || [];
      if (heatLayer) { map.removeLayer(heatLayer); }
      heatLayer = L.heatLayer(points, { radius: 25, blur: 15, maxZoom: 17, pane: "heatPane" });
      if (heatVisible) heatLayer.addTo(map);
    }).catch(function () {});
  }

  /* ---- Impact counter ---- */
  function animateCount(el, target) {
    var start = 0;
    var duration = 900;
    var startTime = null;
    function step(ts) {
      if (!startTime) startTime = ts;
      var progress = Math.min((ts - startTime) / duration, 1);
      var eased = 1 - Math.pow(1 - progress, 3);
      el.textContent = Math.round(start + (target - start) * eased).toLocaleString();
      if (progress < 1) requestAnimationFrame(step);
    }
    requestAnimationFrame(step);
  }

  function loadImpact() {
    if (!config.endpoints || !config.endpoints.impact) return;
    U.fetchJson(config.endpoints.impact).then(function (data) {
      var maps = {
        "impact-bags": data.bags_collected || 0,
        "impact-cleaned": data.sites_cleaned || 0,
        "impact-reported": data.sites_reported || 0,
        "impact-volunteers": data.active_volunteers_this_month || 0,
      };
      Object.keys(maps).forEach(function (id) {
        var el = document.getElementById(id);
        if (el) animateCount(el, maps[id]);
      });
    }).catch(function () {});
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
          radius: p.chronic ? 10 : 8,
          fillColor: statusColor(p.status),
          color: p.chronic ? "#991b1b" : "#fff",
          weight: p.chronic ? 3 : 2,
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
      if (site.chronic) html += '<span class="chronic-badge">Chronic</span>';
      html += '</div></div>';

      if (site.verified_at) {
        html += renderBadge("Verified \u2713", "verified");
      }

      // Trajectory signal (Phase 5D)
      if (site.trajectory && site.trajectory !== "resolved" && site.trajectory !== "stable") {
        var trajLabel = site.trajectory === "worsening" ? "\u2197 Getting worse" : "\u2198 Improving";
        html += '<span class="trajectory-badge trajectory-badge--' + site.trajectory + '">' + trajLabel + '</span> ';
      }
      html += '<dl class="detail-meta-grid">';
      html += renderMeta("Reported by", site.created_by);
      html += renderMeta("Created", formatDate(site.created_at));
      if (site.cleaned_at) html += renderMeta("Cleaned", formatDate(site.cleaned_at));
      if (site.verified_at) {
        html += renderMeta("Verified by", site.verified_by + " on " + formatDate(site.verified_at));
        if (site.work_order) html += renderMeta("Work Order", site.work_order);
      }
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

      // Site history timeline (Phase 6E)
      if (site.timeline && site.timeline.length) {
        var TL_ICONS = { reported: "📍", proof: "📷", cleaned: "🧹", verified: "✅", chronic: "⚠️" };
        html += '<div class="detail-section"><h4>Site History</h4><div class="site-timeline">';
        site.timeline.forEach(function (ev) {
          html += '<div class="timeline-event timeline-event--' + U.escapeHtml(ev.type) + '">';
          html += '<span class="tl-icon" aria-hidden="true">' + (TL_ICONS[ev.type] || "•") + '</span>';
          html += '<div class="tl-body">';
          html += '<span class="tl-label">' + U.escapeHtml(ev.label) + '</span>';
          html += '<span class="tl-meta">by ' + U.escapeHtml(ev.by) + ' &middot; ' + formatDate(ev.at) + '</span>';
          html += '</div></div>';
        });
        html += '</div></div>';
      }

      // Proof notes (bags & notes still shown separately)
      if (site.proofs && site.proofs.length) {
        var proofsWithNotes = site.proofs.filter(function (p) { return p.note || p.bags_count; });
        if (proofsWithNotes.length) {
          html += '<div class="detail-section"><h4>Cleanup Notes</h4><div class="proof-list">';
          proofsWithNotes.forEach(function (proof) {
            html += '<div class="proof-card">';
            html += '<div class="proof-card-top">';
            if (proof.bags_count) html += '<span class="proof-bags">' + proof.bags_count + ' bags</span>';
            html += '<span class="proof-meta">' + U.escapeHtml(proof.created_by) + ' &middot; ' + formatDate(proof.created_at) + '</span>';
            html += '</div>';
            if (proof.note) html += '<p class="proof-note">' + U.escapeHtml(proof.note) + '</p>';
            html += '</div>';
          });
          html += '</div></div>';
        }
      }

      // Mark cleaned button
      if (site.permissions && site.permissions.can_mark_cleaned && site.status !== "CLEANED") {
        html += '<div class="detail-action-row">';
        html += '<button class="btn btn-secondary" data-open-cleaned="' + site.id + '">Mark Cleaned</button>';
        html += '</div>';
      }

      // Verify button (coordinators / admins, cleaned sites not yet verified)
      if (site.permissions && site.permissions.can_verify && site.status === "CLEANED" && !site.verified_at) {
        html += '<div class="detail-action-row">';
        html += '<button class="btn btn-subtle btn-compact" data-verify-site="' + site.id + '">Verify Cleanup</button>';
        html += '</div>';
      }

      // Share button (any site)
      html += '<div class="detail-action-row">';
      html += '<button class="btn btn-subtle btn-compact" data-share-site="' + site.id + '" data-share-title="' + U.escapeHtml(site.title || "Unnamed Site") + '">Share</button>';
      html += '</div>';

      html += '</div>';

      function attachDetailHandlers(container) {
        var cleanBtn = container.querySelector("[data-open-cleaned]");
        if (cleanBtn) {
          cleanBtn.addEventListener("click", function () {
            openCleanedModal(cleanBtn.getAttribute("data-open-cleaned"));
          });
        }
        var verifyBtn = container.querySelector("[data-verify-site]");
        if (verifyBtn) {
          verifyBtn.addEventListener("click", function () {
            openVerifyModal(verifyBtn.getAttribute("data-verify-site"));
          });
        }
        var shareBtn = container.querySelector("[data-share-site]");
        if (shareBtn) {
          shareBtn.addEventListener("click", function () {
            openShareModal(shareBtn.getAttribute("data-share-site"), shareBtn.getAttribute("data-share-title"));
          });
        }
      }

      if (mobile) {
        mobileDetailBody.innerHTML = html;
        attachDetailHandlers(mobileDetailBody);
      } else {
        setDetail(html);
        attachDetailHandlers(detailContent);
      }
    }).catch(function () {
      if (mobile) {
        mobileDetailBody.innerHTML = '<p style="color:var(--color-text-muted)">Unable to load details.</p>';
      } else {
        setDetail('<p style="color:var(--color-text-muted)">Unable to load details.</p>');
      }
    });
  }

  /* ---- Verify cleanup ---- */
  function openVerifyModal(siteId) {
    var note = window.prompt("Verification note (optional):", "");
    if (note === null) return; // cancelled
    var workOrder = window.prompt("Work order number (optional):", "");
    if (workOrder === null) return;

    var url = (config.endpoints && config.endpoints.trashUpdateBase)
      ? config.endpoints.trashUpdateBase + siteId + "/verify/"
      : "/api/trash-sites/" + siteId + "/verify/";

    U.fetchJson(url, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-CSRFToken": U.getCsrfToken() },
      body: JSON.stringify({ verification_note: note, work_order: workOrder }),
    }).then(function () {
      U.showToast("Cleanup verified!", "success");
      showDetail(siteId);
    }).catch(function (err) {
      U.showToast(err.message || "Verification failed.", "error");
    });
  }

  /* ---- Share modal ---- */
  var shareCopyBtn = document.getElementById("share-copy-btn");
  var shareFbBtn = document.getElementById("share-fb-btn");
  var shareXBtn = document.getElementById("share-x-btn");
  var shareModalDesc = document.getElementById("share-modal-desc");

  function openShareModal(siteId, siteTitle) {
    var shareUrl = window.location.origin + "/share/" + siteId + "/";
    var text = (siteTitle || "Unnamed Site") + " was cleaned in Putnam County!";

    if (navigator.share) {
      navigator.share({ title: siteTitle || "Cleanup Result", text: text, url: shareUrl }).catch(function () {});
      return;
    }

    if (shareModalDesc) shareModalDesc.textContent = text;
    if (shareFbBtn) shareFbBtn.href = "https://www.facebook.com/sharer/sharer.php?u=" + encodeURIComponent(shareUrl);
    if (shareXBtn) shareXBtn.href = "https://twitter.com/intent/tweet?url=" + encodeURIComponent(shareUrl) + "&text=" + encodeURIComponent(text);
    if (shareCopyBtn) {
      shareCopyBtn.onclick = function () {
        if (navigator.clipboard) {
          navigator.clipboard.writeText(shareUrl).then(function () {
            U.showToast("Link copied!", "success");
          }).catch(function () {
            U.showToast("Could not copy link.", "error");
          });
        }
      };
    }
    U.openModal("share-modal");
  }

  /* ---- Mode switching ---- */
  var topbarEl = document.querySelector(".topbar");

  function setMode(mode) {
    currentMode = mode;
    cancelReportSubMode();

    modeReportBtn.classList.toggle("is-active", mode === "report");
    modeCleanupBtn.classList.toggle("is-active", mode === "cleanup");
    modeReportBtn.setAttribute("aria-pressed", mode === "report");
    modeCleanupBtn.setAttribute("aria-pressed", mode === "cleanup");

    reportPanel.classList.toggle("hidden", mode !== "report");
    cleanupPanel.classList.toggle("hidden", mode !== "cleanup");

    if (topbarEl) topbarEl.classList.toggle("mode-cleanup", mode === "cleanup");

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
    if (createEventBtn) createEventBtn.classList.remove("is-active");
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
    if (currentMode !== "report") return;

    if (reportSubMode === "event") {
      if (!requireAuth()) return;
      document.getElementById("event-lat").value = e.latlng.lat;
      document.getElementById("event-lng").value = e.latlng.lng;
      U.openModal("event-modal");
      cancelReportSubMode();
      return;
    }

    if (reportSubMode !== "pin") return;
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

    var formData = new FormData(trashForm);

    if (!navigator.onLine) {
      savePendingReport(formData).then(function() {
        trashForm.reset();
        document.getElementById("trash-photo-preview").innerHTML = "";
        U.closeModal("trash-modal");
        U.showToast("Saved offline \u2014 will sync when you reconnect.", "success");
        if (pendingMarker) { map.removeLayer(pendingMarker); pendingMarker = null; }
      }).catch(function() {
        U.showToast("Could not save report locally.", "error");
      });
      return;
    }

    setLoading("trash-submit-btn", true);
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

  /* ---- Cleanup Events ---- */
  function loadEvents() {
    if (!config.endpoints || !config.endpoints.eventsBase) return;
    U.fetchJson(config.endpoints.eventsBase + "?status=SCHEDULED").then(function (data) {
      eventLayer.clearLayers();
      var events = data.results || [];
      events.forEach(function (ev) {
        var coords = ev.coordinates;
        var marker = L.marker([coords[1], coords[0]], {
          icon: L.divIcon({
            className: "",
            html: '<div class="event-map-marker" title="' + U.escapeHtml(ev.title) + '">&#128197;</div>',
            iconSize: [32, 32],
            iconAnchor: [16, 16],
          }),
        });
        marker.on("click", function () {
          showEventDetail(ev.id);
        });
        marker.addTo(eventLayer);
      });
    }).catch(function () {});
  }

  function showEventDetail(eventId) {
    var mobile = isMobileView();
    var loading = '<p style="color:var(--color-text-muted)">Loading\u2026</p>';
    if (mobile) { mobileDetailBody.innerHTML = loading; mobileDetailCard.classList.remove("hidden"); }
    else { setDetail(loading); }

    U.fetchJson(config.endpoints.eventsBase + eventId + "/").then(function (ev) {
      var d = new Date(ev.event_date);
      var dateStr = d.toLocaleDateString(undefined, { weekday: "long", month: "long", day: "numeric", year: "numeric" });
      var timeStr = d.toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit", hour12: true });

      var html = '<div class="detail-panel">';
      html += '<div class="detail-panel-header">';
      html += '<span class="detail-kicker">Cleanup Event</span>';
      html += '<h3>' + U.escapeHtml(ev.title) + '</h3>';
      html += '<div class="detail-badge-row">';
      html += renderBadge(titleCase(ev.status), tokenClass(ev.status));
      if (ev.is_full) html += renderBadge("Full", "hazard");
      html += '</div></div>';

      html += '<dl class="detail-meta-grid">';
      html += renderMeta("Date", dateStr);
      html += renderMeta("Time", timeStr);
      html += renderMeta("Organizer", ev.organizer);
      html += renderMeta("RSVPs", ev.rsvp_count + (ev.max_attendees ? " / " + ev.max_attendees : ""));
      html += '</dl>';

      if (ev.description) {
        html += '<div class="detail-section"><h4>Details</h4>';
        html += '<p class="detail-copy">' + U.escapeHtml(ev.description) + '</p></div>';
      }

      if (ev.status === "SCHEDULED") {
        html += '<div class="detail-action-row">';
        if (!isAuth) {
          html += '<a class="btn btn-primary" href="/accounts/login/">Log in to RSVP</a>';
        } else if (ev.user_has_rsvp) {
          html += '<button class="btn btn-subtle btn-compact" data-cancel-rsvp="' + ev.id + '">Cancel RSVP</button>';
        } else if (!ev.is_full) {
          html += '<button class="btn btn-primary" data-rsvp="' + ev.id + '">RSVP</button>';
        } else {
          html += '<button class="btn btn-subtle btn-compact" disabled>Event Full</button>';
        }
        if (ev.permissions && ev.permissions.can_complete) {
          html += ' <button class="btn btn-subtle btn-compact" data-complete-event="' + ev.id + '">Mark Completed</button>';
        }
        html += '</div>';
      }

      // Get Flyer button (Phase 5I)
      html += '<div class="detail-action-row">';
      html += '<a class="btn btn-subtle btn-compact" href="/api/events/' + ev.id + '/flyer/" target="_blank" rel="noopener">&#128203; Get Flyer</a>';
      html += '</div>';

      html += '</div>';

      function attachEventHandlers(container) {
        var rsvpBtn = container.querySelector("[data-rsvp]");
        if (rsvpBtn) {
          rsvpBtn.addEventListener("click", function () {
            submitRsvp(rsvpBtn.getAttribute("data-rsvp"), true);
          });
        }
        var cancelBtn = container.querySelector("[data-cancel-rsvp]");
        if (cancelBtn) {
          cancelBtn.addEventListener("click", function () {
            submitRsvp(cancelBtn.getAttribute("data-cancel-rsvp"), false);
          });
        }
        var completeBtn = container.querySelector("[data-complete-event]");
        if (completeBtn) {
          completeBtn.addEventListener("click", function () {
            completeEvent(completeBtn.getAttribute("data-complete-event"));
          });
        }
      }

      if (mobile) { mobileDetailBody.innerHTML = html; attachEventHandlers(mobileDetailBody); }
      else { setDetail(html); attachEventHandlers(detailContent); }

    }).catch(function () {
      var err = '<p style="color:var(--color-text-muted)">Unable to load event details.</p>';
      if (isMobileView()) { mobileDetailBody.innerHTML = err; } else { setDetail(err); }
    });
  }

  function submitRsvp(eventId, rsvping) {
    var url = config.endpoints.eventsBase + eventId + "/rsvp/";
    U.fetchJson(url, {
      method: rsvping ? "POST" : "DELETE",
      headers: { "X-CSRFToken": U.getCsrfToken() },
    }).then(function () {
      U.showToast(rsvping ? "RSVP confirmed!" : "RSVP cancelled.", "success");
      showEventDetail(eventId);
    }).catch(function (err) {
      U.showToast(err.message || "Action failed.", "error");
    });
  }

  function completeEvent(eventId) {
    if (!window.confirm("Mark this event as completed?")) return;
    U.fetchJson(config.endpoints.eventsBase + eventId + "/complete/", {
      method: "POST",
      headers: { "X-CSRFToken": U.getCsrfToken() },
    }).then(function () {
      U.showToast("Event marked completed.", "success");
      loadEvents();
      showEventDetail(eventId);
    }).catch(function (err) {
      U.showToast(err.message || "Failed.", "error");
    });
  }

  /* ---- Create Event button ---- */
  if (createEventBtn) {
    createEventBtn.addEventListener("click", function () {
      if (!requireAuth()) return;
      cancelReportSubMode();
      reportSubMode = "event";
      createEventBtn.classList.add("is-active");
      map.getContainer().style.cursor = "crosshair";
      U.announce("Click on the map to set the event location.");
    });
  }

  /* ---- Create Event form ---- */
  var eventForm = document.getElementById("event-form");
  if (eventForm) {
    eventForm.addEventListener("submit", function (e) {
      e.preventDefault();
      if (!requireAuth()) return;
      setLoading("event-submit-btn", true);

      var payload = {
        title: document.getElementById("event-title").value.trim(),
        description: document.getElementById("event-desc").value.trim(),
        event_date: document.getElementById("event-date").value,
        lat: parseFloat(document.getElementById("event-lat").value),
        lng: parseFloat(document.getElementById("event-lng").value),
      };
      var maxVal = document.getElementById("event-max").value;
      if (maxVal) payload.max_attendees = parseInt(maxVal, 10);

      U.fetchJson(config.endpoints.eventsBase, {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-CSRFToken": U.getCsrfToken() },
        body: JSON.stringify(payload),
      }).then(function (ev) {
        eventForm.reset();
        U.closeModal("event-modal");
        U.showToast("Event created!", "success");
        loadEvents();
        showEventDetail(ev.id);
      }).catch(function (err) {
        U.showToast(err.message || "Failed to create event.", "error");
      }).finally(function () {
        setLoading("event-submit-btn", false);
        var lbl = document.querySelector("#event-submit-btn .btn-label");
        if (lbl) lbl.textContent = "Create Event";
      });
    });
  }

  /* ---- Photo previews ---- */
  U.setupPhotoPreview("trash-photos", "trash-photo-preview", 5);
  U.setupPhotoPreview("cleaned-before-photos", "before-photo-preview", 5);
  U.setupPhotoPreview("cleaned-after-photos", "after-photo-preview", 5);

  /* ---- Teams ---- */
  function loadTeams() {
    if (!config.endpoints || !config.endpoints.teamsBase) return;
    U.fetchJson(config.endpoints.teamsBase).then(function(data) {
      var teams = data.results || [];
      ["trash-team", "cleaned-team"].forEach(function(id) {
        var sel = document.getElementById(id);
        if (!sel) return;
        while (sel.options.length > 1) sel.remove(1);
        teams.forEach(function(t) {
          var opt = document.createElement("option");
          opt.value = t.slug;
          opt.textContent = t.name + (t.is_member ? " \u2713" : "");
          sel.appendChild(opt);
        });
      });
    }).catch(function() {});
  }

  /* ---- Offline / IndexedDB ---- */
  var offlineBanner = document.getElementById("offline-banner");

  function showOfflineBanner(show) {
    if (!offlineBanner) return;
    offlineBanner.classList.toggle("hidden", !show);
  }

  if (!navigator.onLine) showOfflineBanner(true);
  window.addEventListener("online", function() {
    showOfflineBanner(false);
    flushPendingReports();
  });
  window.addEventListener("offline", function() { showOfflineBanner(true); });

  function openPendingDB() {
    return new Promise(function(resolve, reject) {
      var req = indexedDB.open("uc-cleanup-pending", 1);
      req.onupgradeneeded = function(e) {
        e.target.result.createObjectStore("reports", {autoIncrement: true});
      };
      req.onsuccess = function(e) { resolve(e.target.result); };
      req.onerror = function() { reject(req.error); };
    });
  }

  function savePendingReport(formData) {
    return new Promise(function(resolve, reject) {
      var data = {};
      var photoPromises = [];
      formData.forEach(function(value, key) {
        if (value instanceof File) {
          var p = new Promise(function(res) {
            var reader = new FileReader();
            reader.onload = function(e) { res({key: key, data: e.target.result, name: value.name, type: value.type}); };
            reader.readAsDataURL(value);
          });
          photoPromises.push(p);
        } else {
          data[key] = value;
        }
      });
      Promise.all(photoPromises).then(function(photos) {
        data.__photos = photos;
        openPendingDB().then(function(db) {
          var tx = db.transaction("reports", "readwrite");
          tx.objectStore("reports").add(data);
          tx.oncomplete = function() { resolve(); };
          tx.onerror = reject;
        }).catch(reject);
      });
    });
  }

  function flushPendingReports() {
    if (!navigator.onLine) return;
    openPendingDB().then(function(db) {
      var tx = db.transaction("reports", "readonly");
      var store = tx.objectStore("reports");
      var allKeys = [], allData = [];
      store.getAllKeys().onsuccess = function(e) { allKeys = e.target.result; };
      store.getAll().onsuccess = function(e) { allData = e.target.result; };
      tx.oncomplete = function() {
        if (!allData.length) return;
        allData.forEach(function(data, i) {
          var key = allKeys[i];
          var fd = new FormData();
          Object.keys(data).forEach(function(k) {
            if (k === "__photos") return;
            fd.append(k, data[k]);
          });
          (data.__photos || []).forEach(function(p) {
            var arr = p.data.split(",");
            var mime = arr[0].match(/:(.*?);/)[1];
            var bstr = atob(arr[1]);
            var u8 = new Uint8Array(bstr.length);
            for (var n = 0; n < bstr.length; n++) u8[n] = bstr.charCodeAt(n);
            fd.append(p.key, new File([u8], p.name, {type: mime}));
          });
          U.fetchJson(config.endpoints.trashCreate, {
            method: "POST",
            headers: {"X-CSRFToken": U.getCsrfToken()},
            body: fd,
          }).then(function() {
            var del = db.transaction("reports", "readwrite");
            del.objectStore("reports").delete(key);
            loadFeatures();
            U.showToast("Pending report synced!", "success");
          }).catch(function() {});
        });
      };
    }).catch(function() {});
  }

  // Listen for SW sync messages
  if ("serviceWorker" in navigator) {
    navigator.serviceWorker.addEventListener("message", function(e) {
      if (e.data && e.data.type === "FLUSH_PENDING") flushPendingReports();
    });
  }

  /* ---- Push Notifications ---- */
  function urlBase64ToUint8Array(b64) {
    var pad = "=".repeat((4 - b64.length % 4) % 4);
    var b64n = (b64 + pad).replace(/-/g, "+").replace(/_/g, "/");
    var raw = atob(b64n);
    var out = new Uint8Array(raw.length);
    for (var i = 0; i < raw.length; i++) out[i] = raw.charCodeAt(i);
    return out;
  }

  var notifyBtn = document.getElementById("enable-notifications-btn");
  if (notifyBtn && "serviceWorker" in navigator && "PushManager" in window) {
    notifyBtn.classList.remove("hidden");
    if (Notification.permission === "granted") {
      notifyBtn.textContent = "\uD83D\uDD14 Notifications On";
      notifyBtn.disabled = true;
    }
    notifyBtn.addEventListener("click", function() {
      Notification.requestPermission().then(function(permission) {
        if (permission !== "granted") {
          U.showToast("Notification permission denied.", "error");
          return;
        }
        U.fetchJson(config.endpoints.pushVapidKey).then(function(data) {
          var vapidKey = data.vapid_public_key;
          navigator.serviceWorker.ready.then(function(reg) {
            return reg.pushManager.subscribe({
              userVisibleOnly: true,
              applicationServerKey: urlBase64ToUint8Array(vapidKey),
            });
          }).then(function(subscription) {
            var sub = subscription.toJSON();
            var center = map.getCenter();
            return U.fetchJson(config.endpoints.pushSubscribe, {
              method: "POST",
              headers: {"Content-Type": "application/json", "X-CSRFToken": U.getCsrfToken()},
              body: JSON.stringify({
                endpoint: sub.endpoint,
                p256dh: sub.keys.p256dh,
                auth: sub.keys.auth,
                lat: center ? center.lat : null,
                lng: center ? center.lng : null,
              }),
            });
          }).then(function() {
            U.showToast("Notifications enabled for reports near your current view.", "success");
            notifyBtn.textContent = "\uD83D\uDD14 Notifications On";
            notifyBtn.disabled = true;
          }).catch(function() {
            U.showToast("Failed to enable notifications.", "error");
          });
        }).catch(function() {
          U.showToast("Push notifications not available on this server.", "error");
        });
      });
    });
  }

  /* ---- Address search (Phase 5A — Nominatim) ---- */
  (function () {
    var searchInput = document.getElementById("search-input");
    var searchResults = document.getElementById("search-results");
    if (!searchInput || !searchResults) return;

    // Putnam County + neighbors bounding box [west,south,east,north]
    var VIEWBOX = "-86.2,36.0,-85.2,36.7";
    var searchTimer = null;
    var focusedIndex = -1;

    function clearResults() {
      searchResults.innerHTML = "";
      searchResults.classList.add("hidden");
      searchInput.setAttribute("aria-expanded", "false");
      focusedIndex = -1;
    }

    function renderResults(results) {
      searchResults.innerHTML = "";
      if (!results.length) {
        clearResults();
        return;
      }
      results.forEach(function (r, i) {
        var li = document.createElement("li");
        li.className = "search-result-item";
        li.setAttribute("role", "option");
        li.setAttribute("id", "search-result-" + i);
        li.textContent = r.display_name;
        li.addEventListener("mousedown", function (e) {
          e.preventDefault(); // prevent input blur before click
          selectResult(r);
        });
        searchResults.appendChild(li);
      });
      searchResults.classList.remove("hidden");
      searchInput.setAttribute("aria-expanded", "true");
      focusedIndex = -1;
    }

    function setFocused(index) {
      var items = searchResults.querySelectorAll(".search-result-item");
      items.forEach(function (el, i) {
        el.classList.toggle("is-focused", i === index);
      });
      focusedIndex = index;
      if (items[index]) {
        searchInput.setAttribute("aria-activedescendant", "search-result-" + index);
      }
    }

    function selectResult(r) {
      var lat = parseFloat(r.lat);
      var lng = parseFloat(r.lon);
      map.flyTo([lat, lng], 16);
      searchInput.value = r.display_name;
      clearResults();

      // Temporary pin that disappears on next map interaction
      var tempPin = L.circleMarker([lat, lng], {
        radius: 10, fillColor: "#0d5e97", color: "#fff", weight: 3, fillOpacity: 0.85,
      }).addTo(map);
      tempPin.bindPopup(r.display_name || "Search result").openPopup();
      map.once("movestart", function () {
        if (tempPin) map.removeLayer(tempPin);
      });
    }

    function doSearch(query) {
      var url = "https://nominatim.openstreetmap.org/search"
        + "?q=" + encodeURIComponent(query)
        + "&countrycodes=us"
        + "&viewbox=" + VIEWBOX
        + "&bounded=0"
        + "&format=json"
        + "&limit=5"
        + "&addressdetails=0";

      fetch(url, {
        headers: { "Accept-Language": "en", "User-Agent": "UC-CleanUp/1.0 (uc-cleanup.com)" },
      }).then(function (r) { return r.json(); }).then(function (data) {
        renderResults(data || []);
      }).catch(function () { clearResults(); });
    }

    searchInput.addEventListener("input", function () {
      clearTimeout(searchTimer);
      var q = searchInput.value.trim();
      if (q.length < 3) { clearResults(); return; }
      searchTimer = setTimeout(function () { doSearch(q); }, 400);
    });

    searchInput.addEventListener("keydown", function (e) {
      var items = searchResults.querySelectorAll(".search-result-item");
      if (e.key === "ArrowDown") {
        e.preventDefault();
        setFocused(Math.min(focusedIndex + 1, items.length - 1));
      } else if (e.key === "ArrowUp") {
        e.preventDefault();
        setFocused(Math.max(focusedIndex - 1, 0));
      } else if (e.key === "Enter") {
        if (focusedIndex >= 0 && items[focusedIndex]) {
          items[focusedIndex].dispatchEvent(new MouseEvent("mousedown"));
        }
        e.preventDefault();
      } else if (e.key === "Escape") {
        clearResults();
      }
    });

    searchInput.addEventListener("blur", function () {
      // Delay so mousedown on result fires first
      setTimeout(clearResults, 150);
    });
  }());

  /* ---- Init ---- */
  setMode("report");
  loadDistricts();
  loadFeatures();
  loadHeatmap();
  loadImpact();
  loadEvents();
  loadTeams();

  // Deep link to a specific site from URL params
  var params = new URLSearchParams(window.location.search);
  var focusId = params.get("focus_id");
  if (focusId) {
    showDetail(focusId);
  }
})();
