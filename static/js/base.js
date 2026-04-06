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
