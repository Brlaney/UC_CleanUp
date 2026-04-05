(function () {
  const config = window.APP_CONFIG;
  const rootStyles = getComputedStyle(document.documentElement);

  function cssVar(name, fallback) {
    const value = rootStyles.getPropertyValue(name).trim();
    return value || fallback;
  }

  const MAP_COLORS = {
    pending: cssVar("--map-marker-pending", "#db5a26"),
    inProgress: cssVar("--map-marker-in-progress", "#ccb10f"),
    cleaned: cssVar("--map-marker-cleaned", "#1f944f"),
    route: cssVar("--map-route-color", "#2967ad"),
    routeDraw: cssVar("--map-route-draw-color", "#2474cc"),
    countyBoundary: cssVar("--map-county-boundary", "#0e5ea8"),
    countyBoundaryFill: cssVar("--map-county-boundary-fill", "rgba(14, 94, 168, 0.1)"),
    outsideMask: cssVar("--map-outside-mask-color", "#081421"),
    outsideMaskOpacity: Number(cssVar("--map-outside-mask-opacity", "0.62")) || 0.62,
  };

  const map = L.map("map").setView([36.1627, -85.5016], 12);
  map.createPane("countyMaskPane");
  map.getPane("countyMaskPane").style.zIndex = "340";
  map.createPane("countyBoundaryPane");
  map.getPane("countyBoundaryPane").style.zIndex = "350";
  const trashLayer = L.layerGroup().addTo(map);
  const routeLayer = L.layerGroup().addTo(map);
  const mapLayerSelect = document.getElementById("map-layer-select");
  const overlayPutnamToggle = document.getElementById("overlay-putnam-toggle");
  const overlaySixCountyToggle = document.getElementById("overlay-six-county-toggle");
  const overlayUpperToggle = document.getElementById("overlay-upper-toggle");
  const overlayCustomToggle = document.getElementById("overlay-custom-toggle");
  const countyBoundaryCheckboxes = Array.from(
    document.querySelectorAll('input[name="county-boundary"]')
  );
  const customCountyListWrap = document.getElementById("custom-county-list-wrap");
  const drawHandler = new L.Draw.Polyline(map, {
    shapeOptions: { color: MAP_COLORS.routeDraw, weight: 5, opacity: 0.92 },
  });

  let reportMode = false;
  let pendingRouteLayer = null;
  let activeBaseLayer = null;
  let countyOutsideMaskLayer = null;
  let countyBoundariesLoaded = false;
  const countyBoundaryLayersByName = new Map();
  const countyBoundaryGeometryByName = new Map();
  const WORLD_RING = [
    [85, -180],
    [85, 180],
    [-85, 180],
    [-85, -180],
  ];
  const SIX_COUNTY_PRESET = ["Smith", "Jackson", "Putnam", "White", "Van Buren", "Cumberland"];
  const overlayModeToggles = [
    overlayPutnamToggle,
    overlaySixCountyToggle,
    overlayUpperToggle,
    overlayCustomToggle,
  ].filter(Boolean);

  const BASEMAP_CONFIG = {
    osm_standard: {
      url: "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",
      options: {
        maxZoom: 19,
        attribution: "&copy; OpenStreetMap contributors",
      },
    },
    osm_humanitarian: {
      url: "https://{s}.tile.openstreetmap.fr/hot/{z}/{x}/{y}.png",
      options: {
        maxZoom: 19,
        attribution: "&copy; OpenStreetMap contributors, HOT",
      },
    },
    carto_light: {
      url: "https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png",
      options: {
        maxZoom: 20,
        subdomains: "abcd",
        attribution: "&copy; OpenStreetMap contributors, &copy; CARTO",
      },
    },
    carto_dark: {
      url: "https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png",
      options: {
        maxZoom: 20,
        subdomains: "abcd",
        attribution: "&copy; OpenStreetMap contributors, &copy; CARTO",
      },
    },
    esri_imagery: {
      url: "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
      options: {
        maxZoom: 19,
        attribution: "Tiles &copy; Esri",
      },
    },
  };

  function setBaseLayer(layerKey) {
    const selectedKey = BASEMAP_CONFIG[layerKey] ? layerKey : "osm_standard";
    if (activeBaseLayer) {
      map.removeLayer(activeBaseLayer);
    }
    const layerConfig = BASEMAP_CONFIG[selectedKey];
    activeBaseLayer = L.tileLayer(layerConfig.url, layerConfig.options);
    activeBaseLayer.addTo(map);
  }

  function buildCountyBoundaryLayer(feature) {
    const countyName = feature?.properties?.NAME || "County";
    const layer = L.geoJSON(feature, {
      pane: "countyBoundaryPane",
      style: {
        color: MAP_COLORS.countyBoundary,
        weight: 3,
        fillColor: MAP_COLORS.countyBoundaryFill,
        fillOpacity: 0.12,
      },
    });
    layer.bindTooltip(`${countyName} County`, { sticky: true });
    return layer;
  }

  function ringToLatLngs(ringCoordinates) {
    return ringCoordinates.map((point) => [point[1], point[0]]);
  }

  function getOuterRingsFromGeometry(geometry) {
    if (!geometry) {
      return [];
    }
    if (geometry.type === "Polygon") {
      if (!Array.isArray(geometry.coordinates) || geometry.coordinates.length === 0) {
        return [];
      }
      return [ringToLatLngs(geometry.coordinates[0])];
    }
    if (geometry.type === "MultiPolygon") {
      const rings = [];
      (geometry.coordinates || []).forEach((polygon) => {
        if (Array.isArray(polygon) && polygon.length > 0) {
          rings.push(ringToLatLngs(polygon[0]));
        }
      });
      return rings;
    }
    return [];
  }

  function buildOutsideMaskLayer(selectedCountyNames) {
    const holeRings = [];
    selectedCountyNames.forEach((countyName) => {
      const geometry = countyBoundaryGeometryByName.get(countyName);
      getOuterRingsFromGeometry(geometry).forEach((ring) => {
        holeRings.push(ring);
      });
    });
    if (holeRings.length === 0) {
      return null;
    }
    return L.polygon([WORLD_RING, ...holeRings], {
      pane: "countyMaskPane",
      stroke: false,
      fillColor: MAP_COLORS.outsideMask,
      fillOpacity: MAP_COLORS.outsideMaskOpacity,
      interactive: false,
    });
  }

  async function ensureCountyBoundaryLayers() {
    if (countyBoundariesLoaded) {
      return countyBoundaryLayersByName;
    }
    const response = await fetch(config.endpoints.countyBoundariesGeoJson, {
      credentials: "same-origin",
    });
    if (!response.ok) {
      throw new Error("Unable to load county boundary overlays.");
    }
    const geojsonPayload = await response.json();
    (geojsonPayload.features || []).forEach((feature) => {
      const countyName = feature?.properties?.NAME;
      if (!countyName || countyBoundaryLayersByName.has(countyName)) {
        return;
      }
      countyBoundaryGeometryByName.set(countyName, feature?.geometry || null);
      countyBoundaryLayersByName.set(countyName, buildCountyBoundaryLayer(feature));
    });
    countyBoundariesLoaded = true;
    return countyBoundaryLayersByName;
  }

  function syncCustomCountyListVisibility() {
    if (!customCountyListWrap) {
      return;
    }
    const isCustomEnabled = overlayCustomToggle && overlayCustomToggle.checked;
    customCountyListWrap.classList.toggle("is-hidden", !isCustomEnabled);
  }

  function ensureOverlayModeSelection(activeToggle) {
    if (activeToggle && activeToggle.checked) {
      overlayModeToggles.forEach((toggle) => {
        if (toggle !== activeToggle) {
          toggle.checked = false;
        }
      });
      return;
    }

    if (!overlayModeToggles.some((toggle) => toggle.checked) && overlayPutnamToggle) {
      overlayPutnamToggle.checked = true;
    }
  }

  function getSelectedCountyNames() {
    if (overlayUpperToggle && overlayUpperToggle.checked) {
      return new Set(Array.from(countyBoundaryLayersByName.keys()));
    }

    if (overlaySixCountyToggle && overlaySixCountyToggle.checked) {
      return new Set(SIX_COUNTY_PRESET);
    }

    if (overlayCustomToggle && overlayCustomToggle.checked) {
      const selected = new Set();
      countyBoundaryCheckboxes.forEach((checkbox) => {
        if (checkbox.checked) {
          selected.add(checkbox.value);
        }
      });
      return selected;
    }

    const selected = new Set();
    if (!overlayPutnamToggle || overlayPutnamToggle.checked) {
      selected.add("Putnam");
    }
    return selected;
  }

  async function syncCountyBoundaryVisibility() {
    await ensureCountyBoundaryLayers();
    const selectedCountyNames = getSelectedCountyNames();

    countyBoundaryLayersByName.forEach((layer, countyName) => {
      if (selectedCountyNames.has(countyName)) {
        if (!map.hasLayer(layer)) {
          layer.addTo(map);
        }
      } else if (map.hasLayer(layer)) {
        map.removeLayer(layer);
      }
    });

    if (countyOutsideMaskLayer && map.hasLayer(countyOutsideMaskLayer)) {
      map.removeLayer(countyOutsideMaskLayer);
      countyOutsideMaskLayer = null;
    }
    countyOutsideMaskLayer = buildOutsideMaskLayer(selectedCountyNames);
    if (countyOutsideMaskLayer) {
      countyOutsideMaskLayer.addTo(map);
    }
  }

  setBaseLayer(mapLayerSelect ? mapLayerSelect.value : "osm_humanitarian");
  if (mapLayerSelect) {
    mapLayerSelect.addEventListener("change", function () {
      setBaseLayer(mapLayerSelect.value);
    });
  }
  function handleOverlayModeToggleChange(activeToggle) {
    ensureOverlayModeSelection(activeToggle);
    syncCustomCountyListVisibility();
    syncCountyBoundaryVisibility().catch((error) => {
      setDetailHtml(renderDetailNotice("Overlay error", error.message));
    });
  }

  overlayModeToggles.forEach((toggle) => {
    toggle.addEventListener("change", function () {
      handleOverlayModeToggleChange(toggle);
    });
  });
  countyBoundaryCheckboxes.forEach((checkbox) => {
    checkbox.addEventListener("change", function () {
      syncCountyBoundaryVisibility().catch((error) => {
        setDetailHtml(renderDetailNotice("Overlay error", error.message));
      });
    });
  });

  function getCsrfToken() {
    const match = document.cookie
      .split(";")
      .map((v) => v.trim())
      .find((v) => v.startsWith("csrftoken="));
    return match ? decodeURIComponent(match.split("=")[1]) : "";
  }

  function statusColor(status) {
    if (status === "CLEANED") {
      return MAP_COLORS.cleaned;
    }
    if (status === "IN_PROGRESS") {
      return MAP_COLORS.inProgress;
    }
    return MAP_COLORS.pending;
  }

  function openModal(id) {
    document.getElementById(id).classList.remove("hidden");
  }

  function closeModal(id) {
    document.getElementById(id).classList.add("hidden");
  }

  function getFilterStatusCsv() {
    const selected = [];
    document.querySelectorAll('input[name="status"]:checked').forEach((item) => selected.push(item.value));
    return selected.join(",");
  }

  function getDaysFilter() {
    return document.getElementById("days-filter").value;
  }

  function getBBoxString() {
    const bounds = map.getBounds();
    return [
      bounds.getWest().toFixed(6),
      bounds.getSouth().toFixed(6),
      bounds.getEast().toFixed(6),
      bounds.getNorth().toFixed(6),
    ].join(",");
  }

  function escapeHtml(text) {
    if (!text) {
      return "";
    }
    return String(text)
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#39;");
  }

  function titleCaseToken(value) {
    if (!value) {
      return "";
    }
    return String(value)
      .toLowerCase()
      .split("_")
      .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
      .join(" ");
  }

  function tokenClass(value) {
    return String(value || "")
      .toLowerCase()
      .replaceAll("_", "-");
  }

  function formatDateTime(value) {
    if (!value) {
      return "n/a";
    }
    const parsed = new Date(value);
    if (Number.isNaN(parsed.getTime())) {
      return String(value);
    }
    return parsed.toLocaleString();
  }

  function renderDetailNotice(title, message) {
    return `
      <div class="detail-empty-state">
        <span class="detail-empty-kicker">${escapeHtml(title)}</span>
        <h3>${escapeHtml(message)}</h3>
      </div>
    `;
  }

  function renderDetailBadge(label, modifierClass) {
    return `<span class="detail-badge ${modifierClass}">${escapeHtml(label)}</span>`;
  }

  function renderMetaItem(label, value) {
    return `
      <div class="detail-meta-item">
        <dt>${escapeHtml(label)}</dt>
        <dd>${escapeHtml(value)}</dd>
      </div>
    `;
  }

  function renderProofs(proofs) {
    if (!proofs || proofs.length === 0) {
      return '<div class="detail-inline-empty">No proof entries yet.</div>';
    }
    return `
      <div class="proof-list">
        ${proofs
          .map((proof) => {
            const photos = (proof.photos || [])
              .map((url) => `<img src="${url}" alt="proof photo" loading="lazy">`)
              .join("");
            return `
              <article class="proof-card">
                <div class="proof-card-top">
                  <span class="proof-bags">${escapeHtml(String(proof.bags_count))} bags</span>
                  <span class="proof-meta">${escapeHtml(formatDateTime(proof.created_at))}</span>
                </div>
                <p class="proof-note">${escapeHtml(proof.note || "No note added.")}</p>
                <p class="proof-meta">By ${escapeHtml(proof.created_by)}</p>
                ${photos ? `<div class="proof-photo-grid">${photos}</div>` : ""}
              </article>
            `;
          })
          .join("")}
      </div>
    `;
  }

  async function fetchJson(url, options) {
    const response = await fetch(url, options);
    if (!response.ok) {
      let message = "Request failed.";
      try {
        const payload = await response.json();
        message = payload.error || message;
      } catch (_error) {}
      throw new Error(message);
    }
    return response.json();
  }

  function setDetailHtml(html) {
    document.getElementById("detail-content").innerHTML = html;
  }

  function scrollDetailIntoView() {
    const detailContent = document.getElementById("detail-content");
    if (detailContent) {
      detailContent.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  }

  function getFocusRequest() {
    const params = new URLSearchParams(window.location.search);
    const focusType = params.get("focus_type");
    const focusId = params.get("focus_id");
    if (!focusType || !focusId) {
      return null;
    }
    return { focusType, focusId };
  }

  async function showTrashSiteDetail(siteId) {
    try {
      const site = await fetchJson(`${config.endpoints.trashUpdateBase}${siteId}/detail/`);
      const badges = [renderDetailBadge(titleCaseToken(site.status), `detail-badge--${tokenClass(site.status)}`)];
      if (site.severity) {
        badges.push(
          renderDetailBadge(
            `${titleCaseToken(site.severity)} severity`,
            `detail-badge--${tokenClass(site.severity)}`
          )
        );
      }
      if (site.hazard_flag) {
        badges.push(renderDetailBadge("Hazard flagged", "detail-badge--hazard"));
      }
      const cleanedButton =
        site.status !== "CLEANED" && site.permissions && site.permissions.can_mark_cleaned
          ? `<button class="btn btn-secondary" id="detail-mark-cleaned-btn" type="button" data-site-id="${site.id}">Mark Cleaned</button>`
          : "";
      setDetailHtml(`
        <div class="detail-panel">
          <div class="detail-panel-header">
            <div>
              <span class="detail-kicker">Trash Site</span>
              <h3>${escapeHtml(site.title || "Trash Site")}</h3>
            </div>
            <div class="detail-badge-row">${badges.join("")}</div>
          </div>
          <dl class="detail-meta-grid">
            ${renderMetaItem("Reported by", site.created_by)}
            ${renderMetaItem("Created", formatDateTime(site.created_at))}
            ${renderMetaItem("Last updated", formatDateTime(site.updated_at))}
            ${renderMetaItem("Cleaned at", site.cleaned_at ? formatDateTime(site.cleaned_at) : "Not yet cleaned")}
          </dl>
          <div class="detail-section">
            <h4>Description</h4>
            <p class="detail-copy${site.description ? "" : " detail-copy--muted"}">${escapeHtml(
              site.description || "No description added yet."
            )}</p>
          </div>
          ${cleanedButton ? `<div class="detail-action-row">${cleanedButton}</div>` : ""}
          <div class="detail-section">
            <h4>Cleanup Proofs</h4>
            ${renderProofs(site.proofs)}
          </div>
        </div>
      `);
      scrollDetailIntoView();
      const cleanedBtn = document.getElementById("detail-mark-cleaned-btn");
      if (cleanedBtn) {
        cleanedBtn.addEventListener("click", function () {
          document.getElementById("cleaned-site-id").value = cleanedBtn.dataset.siteId;
          openModal("cleaned-modal");
        });
      }
    } catch (error) {
      setDetailHtml(renderDetailNotice("Unable to load details", error.message));
    }
  }

  async function showRouteDetail(routeId) {
    try {
      const route = await fetchJson(`/api/route-cleanups/${routeId}/detail/`);
      const badges = [
        renderDetailBadge(titleCaseToken(route.status), `detail-badge--${tokenClass(route.status)}`),
      ];
      setDetailHtml(`
        <div class="detail-panel">
          <div class="detail-panel-header">
            <div>
              <span class="detail-kicker">Cleanup Route</span>
              <h3>Cleanup Route</h3>
            </div>
            <div class="detail-badge-row">${badges.join("")}</div>
          </div>
          <dl class="detail-meta-grid">
            ${renderMetaItem("Distance", `${Number(route.distance_miles).toFixed(2)} miles`)}
            ${renderMetaItem("Time", route.time_spent_minutes ? `${route.time_spent_minutes} minutes` : "n/a")}
            ${renderMetaItem("Logged by", route.created_by)}
            ${renderMetaItem("Created", formatDateTime(route.created_at))}
          </dl>
          <div class="detail-section">
            <h4>Route Notes</h4>
            <p class="detail-copy${route.notes ? "" : " detail-copy--muted"}">${escapeHtml(
              route.notes || "No notes added for this route."
            )}</p>
          </div>
          <div class="detail-section">
            <h4>Proofs</h4>
            ${renderProofs(route.proofs)}
          </div>
        </div>
      `);
      scrollDetailIntoView();
    } catch (error) {
      setDetailHtml(renderDetailNotice("Unable to load details", error.message));
    }
  }

  function buildTrashPopup(siteProps) {
    const title = escapeHtml(siteProps.title || "Trash Site");
    const cleanedButton =
      siteProps.status !== "CLEANED" && siteProps.can_mark_cleaned
        ? `<button type="button" class="btn btn-secondary btn-compact popup-clean-btn" data-site-id="${siteProps.id}">Mark Cleaned</button>`
        : "";
    return `
      <div class="map-popup">
        <strong>${title}</strong>
        <span class="popup-status popup-status--${tokenClass(siteProps.status)}">${escapeHtml(
          titleCaseToken(siteProps.status)
        )}</span>
        ${cleanedButton}
      </div>
    `;
  }

  function attachPopupCleanHandler(layer) {
    layer.on("popupopen", function (event) {
      const popupEl = event.popup.getElement();
      const btn = popupEl ? popupEl.querySelector(".popup-clean-btn") : null;
      if (btn) {
        btn.addEventListener("click", function () {
          document.getElementById("cleaned-site-id").value = btn.dataset.siteId;
          openModal("cleaned-modal");
        });
      }
    });
  }

  async function loadFeatures() {
    const params = new URLSearchParams({
      bbox: getBBoxString(),
      status: getFilterStatusCsv(),
      days: getDaysFilter(),
    });
    const payload = await fetchJson(`${config.endpoints.features}?${params.toString()}`);

    trashLayer.clearLayers();
    routeLayer.clearLayers();

    (payload.features || []).forEach((feature) => {
      const kind = feature.properties.type;
      if (kind === "trash_site") {
        const marker = L.circleMarker(
          [feature.geometry.coordinates[1], feature.geometry.coordinates[0]],
          {
            radius: 8,
            color: "#ffffff",
            fillColor: statusColor(feature.properties.status),
            fillOpacity: 0.95,
            weight: 2.5,
          }
        );
        marker.bindPopup(buildTrashPopup(feature.properties));
        attachPopupCleanHandler(marker);
        marker.on("click", function () {
          showTrashSiteDetail(feature.properties.id);
        });
        marker.addTo(trashLayer);
      }

      if (kind === "route_cleanup") {
        const routePoints = feature.geometry.coordinates.map((coord) => [coord[1], coord[0]]);
        const routeGroup = L.layerGroup();
        const polyline = L.polyline(routePoints, {
          color: MAP_COLORS.route,
          weight: 5,
          opacity: 0.9,
          lineCap: "round",
          lineJoin: "round",
        });
        polyline.on("click", function () {
          showRouteDetail(feature.properties.id);
        });
        polyline.bindPopup(
          `<strong>Cleanup Route</strong><br><small>${Number(feature.properties.distance_miles).toFixed(
            2
          )} miles</small>`
        );
        polyline.addTo(routeGroup);

        if (routePoints.length >= 2) {
          const startMarker = L.circleMarker(routePoints[0], {
            radius: 5.5,
            color: "#ffffff",
            weight: 2,
            fillColor: MAP_COLORS.route,
            fillOpacity: 1,
          }).bindTooltip("Start", { direction: "top", opacity: 0.92 });
          const endMarker = L.circleMarker(routePoints[routePoints.length - 1], {
            radius: 5.5,
            color: "#ffffff",
            weight: 2,
            fillColor: MAP_COLORS.cleaned,
            fillOpacity: 1,
          }).bindTooltip("End", { direction: "top", opacity: 0.92 });
          [startMarker, endMarker].forEach((endpointMarker) => {
            endpointMarker.on("click", function () {
              showRouteDetail(feature.properties.id);
            });
            endpointMarker.addTo(routeGroup);
          });
        }

        routeGroup.addTo(routeLayer);
      }
    });
  }

  async function focusRequestedFeature() {
    const focusRequest = getFocusRequest();
    if (!focusRequest) {
      return;
    }

    if (focusRequest.focusType === "trash_site") {
      const site = await fetchJson(`${config.endpoints.trashUpdateBase}${focusRequest.focusId}/detail/`);
      map.setView([site.coordinates[1], site.coordinates[0]], 15);
      await loadFeatures();
      await showTrashSiteDetail(focusRequest.focusId);
      return;
    }

    if (focusRequest.focusType === "route_cleanup") {
      const route = await fetchJson(`/api/route-cleanups/${focusRequest.focusId}/detail/`);
      const bounds = L.latLngBounds(route.coordinates.map((coord) => [coord[1], coord[0]]));
      map.fitBounds(bounds.pad(0.2));
      await loadFeatures();
      await showRouteDetail(focusRequest.focusId);
    }
  }

  async function handleTrashCreate(event) {
    event.preventDefault();
    const form = event.currentTarget;
    const formData = new FormData(form);
    await fetchJson(config.endpoints.trashCreate, {
      method: "POST",
      headers: { "X-CSRFToken": getCsrfToken() },
      body: formData,
      credentials: "same-origin",
    });
    form.reset();
    closeModal("trash-modal");
    await loadFeatures();
  }

  async function handleMarkCleaned(event) {
    event.preventDefault();
    const siteId = document.getElementById("cleaned-site-id").value;
    if (!siteId) {
      return;
    }
    const formData = new FormData(event.currentTarget);
    await fetchJson(`${config.endpoints.trashUpdateBase}${siteId}/mark-cleaned/`, {
      method: "POST",
      headers: { "X-CSRFToken": getCsrfToken() },
      body: formData,
      credentials: "same-origin",
    });
    event.currentTarget.reset();
    closeModal("cleaned-modal");
    await showTrashSiteDetail(siteId);
    await loadFeatures();
  }

  async function handleRouteCreate(event) {
    event.preventDefault();
    const form = event.currentTarget;
    const coords = document.getElementById("route-coordinates").value;
    if (!coords) {
      alert("Draw a route first.");
      return;
    }
    const formData = new FormData(form);
    formData.set("coordinates", coords);

    await fetchJson(config.endpoints.routeCreate, {
      method: "POST",
      headers: { "X-CSRFToken": getCsrfToken() },
      body: formData,
      credentials: "same-origin",
    });

    if (pendingRouteLayer) {
      map.removeLayer(pendingRouteLayer);
      pendingRouteLayer = null;
    }
    form.reset();
    document.getElementById("route-coordinates").value = "";
    closeModal("route-modal");
    await loadFeatures();
  }

  function enableReportMode() {
    reportMode = true;
    document.getElementById("report-trash-btn").textContent = "Click Map to Place Pin";
  }

  function disableReportMode() {
    reportMode = false;
    document.getElementById("report-trash-btn").textContent = "Report Trash";
  }

  map.on("click", function (event) {
    if (!reportMode) {
      return;
    }
    document.getElementById("trash-lat").value = event.latlng.lat.toFixed(7);
    document.getElementById("trash-lng").value = event.latlng.lng.toFixed(7);
    openModal("trash-modal");
    disableReportMode();
  });

  map.on(L.Draw.Event.CREATED, function (event) {
    if (event.layerType !== "polyline") {
      return;
    }
    if (pendingRouteLayer) {
      map.removeLayer(pendingRouteLayer);
    }
    pendingRouteLayer = event.layer.addTo(map);
    const coords = event.layer.getLatLngs().map((latlng) => [latlng.lng, latlng.lat]);
    document.getElementById("route-coordinates").value = JSON.stringify(coords);
    openModal("route-modal");
  });

  document.querySelectorAll("[data-close-modal]").forEach((button) => {
    button.addEventListener("click", function () {
      closeModal(button.dataset.closeModal);
      disableReportMode();
    });
  });

  document.getElementById("apply-filters-btn").addEventListener("click", function () {
    loadFeatures().catch((error) => alert(error.message));
  });
  document.getElementById("report-trash-btn").addEventListener("click", function () {
    if (reportMode) {
      disableReportMode();
      return;
    }
    enableReportMode();
  });
  document.getElementById("log-route-btn").addEventListener("click", function () {
    drawHandler.enable();
  });

  document.getElementById("trash-form").addEventListener("submit", function (event) {
    handleTrashCreate(event).catch((error) => alert(error.message));
  });
  document.getElementById("cleaned-form").addEventListener("submit", function (event) {
    handleMarkCleaned(event).catch((error) => alert(error.message));
  });
  document.getElementById("route-form").addEventListener("submit", function (event) {
    handleRouteCreate(event).catch((error) => alert(error.message));
  });

  map.on("moveend zoomend", function () {
    loadFeatures().catch((error) => {
      setDetailHtml(renderDetailNotice("Map error", error.message));
    });
  });

  ensureOverlayModeSelection(null);
  syncCustomCountyListVisibility();
  syncCountyBoundaryVisibility().catch((error) => {
    setDetailHtml(renderDetailNotice("Overlay error", error.message));
  });
  loadFeatures()
    .then(function () {
      return focusRequestedFeature();
    })
    .catch((error) => {
      setDetailHtml(renderDetailNotice("Map error", error.message));
    });
})();
