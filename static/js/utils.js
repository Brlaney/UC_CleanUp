/**
 * Shared utility functions for the District 3 CleanUp app.
 */
(function () {
  "use strict";

  function getCsrfToken() {
    var meta = document.querySelector('meta[name="csrf-token"]');
    if (meta) return meta.getAttribute("content");
    var match = document.cookie
      .split(";")
      .map(function (v) { return v.trim(); })
      .find(function (v) { return v.startsWith("csrftoken="); });
    return match ? decodeURIComponent(match.split("=")[1]) : "";
  }

  function escapeHtml(text) {
    if (!text) return "";
    var div = document.createElement("div");
    div.appendChild(document.createTextNode(text));
    return div.innerHTML;
  }

  /* ---- Toast notifications ---- */

  function showToast(message, type) {
    type = type || "info";
    var container = document.getElementById("toast-container");
    if (!container) return;
    var toast = document.createElement("div");
    toast.className = "toast toast--" + type;
    toast.setAttribute("role", "status");
    toast.textContent = message;
    container.appendChild(toast);
    setTimeout(function () {
      toast.style.opacity = "0";
      toast.style.transition = "opacity 0.3s ease";
      setTimeout(function () { toast.remove(); }, 300);
    }, 4000);
  }

  /* ---- Modal focus management ---- */

  var _focusReturnTarget = null;
  var _activeTrapHandler = null;

  function openModal(id) {
    var modal = document.getElementById(id);
    if (!modal) return;
    _focusReturnTarget = document.activeElement;
    modal.classList.remove("hidden");
    var focusable = modal.querySelectorAll(
      'a[href], button:not([disabled]), textarea, input:not([type="hidden"]), select, [tabindex]:not([tabindex="-1"])'
    );
    if (focusable.length) focusable[0].focus();

    _activeTrapHandler = function (e) {
      if (e.key === "Escape") {
        closeModal(id);
        return;
      }
      if (e.key !== "Tab") return;
      var first = focusable[0];
      var last = focusable[focusable.length - 1];
      if (e.shiftKey) {
        if (document.activeElement === first) { e.preventDefault(); last.focus(); }
      } else {
        if (document.activeElement === last) { e.preventDefault(); first.focus(); }
      }
    };
    document.addEventListener("keydown", _activeTrapHandler);
  }

  function closeModal(id) {
    var modal = document.getElementById(id);
    if (!modal) return;
    modal.classList.add("hidden");
    if (_activeTrapHandler) {
      document.removeEventListener("keydown", _activeTrapHandler);
      _activeTrapHandler = null;
    }
    if (_focusReturnTarget) {
      _focusReturnTarget.focus();
      _focusReturnTarget = null;
    }
  }

  /* ---- Async fetch wrapper ---- */

  function fetchJson(url, options) {
    options = options || {};
    options.credentials = "same-origin";
    return fetch(url, options).then(function (response) {
      return response.json().then(function (data) {
        if (!response.ok) {
          var msg = data.error || "Request failed.";
          throw new Error(msg);
        }
        return data;
      });
    });
  }

  /* ---- Photo preview ---- */

  function setupPhotoPreview(inputId, previewId, maxCount) {
    maxCount = maxCount || 5;
    var input = document.getElementById(inputId);
    var preview = document.getElementById(previewId);
    if (!input || !preview) return;

    input.addEventListener("change", function () {
      preview.innerHTML = "";
      var files = Array.from(input.files).slice(0, maxCount);
      if (input.files.length > maxCount) {
        showToast("Maximum " + maxCount + " photos allowed. Only the first " + maxCount + " will be used.", "error");
        var dt = new DataTransfer();
        files.forEach(function (f) { dt.items.add(f); });
        input.files = dt.files;
      }
      files.forEach(function (file) {
        var img = document.createElement("img");
        img.alt = "Upload preview";
        img.src = URL.createObjectURL(file);
        preview.appendChild(img);
      });
    });
  }

  /* ---- Screen reader announce ---- */

  function announce(message) {
    var el = document.getElementById("mode-instructions");
    if (el) el.textContent = message;
  }

  /* ---- Expose ---- */

  window.AppUtils = {
    getCsrfToken: getCsrfToken,
    escapeHtml: escapeHtml,
    showToast: showToast,
    openModal: openModal,
    closeModal: closeModal,
    fetchJson: fetchJson,
    setupPhotoPreview: setupPhotoPreview,
    announce: announce,
  };
})();
