(function () {
  const config = window.APP_BASE_CONFIG;
  const feedbackModal = document.getElementById("feedback-modal");
  const feedbackOpenButton = document.getElementById("feedback-open-btn");
  const feedbackForm = document.getElementById("feedback-form");
  const feedbackStatus = document.getElementById("feedback-status");
  const feedbackPageUrl = document.getElementById("feedback-page-url");

  function getCsrfToken() {
    const match = document.cookie
      .split(";")
      .map((value) => value.trim())
      .find((value) => value.startsWith("csrftoken="));
    return match ? decodeURIComponent(match.split("=")[1]) : "";
  }

  function openModal() {
    if (!feedbackModal) {
      return;
    }
    if (feedbackPageUrl) {
      feedbackPageUrl.value = window.location.pathname + window.location.search;
    }
    feedbackModal.classList.remove("hidden");
  }

  function closeModal() {
    if (!feedbackModal) {
      return;
    }
    feedbackModal.classList.add("hidden");
  }

  function setStatus(message, state) {
    if (!feedbackStatus) {
      return;
    }
    feedbackStatus.textContent = message || "";
    feedbackStatus.classList.remove("is-error", "is-success");
    if (state) {
      feedbackStatus.classList.add(state);
    }
  }

  async function submitFeedback(event) {
    event.preventDefault();
    const formData = new FormData(feedbackForm);
    setStatus("");
    const response = await fetch(config.endpoints.feedbackCreate, {
      method: "POST",
      headers: {
        "X-CSRFToken": getCsrfToken(),
      },
      body: formData,
      credentials: "same-origin",
    });
    const payload = await response.json();
    if (!response.ok) {
      setStatus(payload.error || "Unable to send feedback.", "is-error");
      return;
    }
    feedbackForm.reset();
    if (feedbackPageUrl) {
      feedbackPageUrl.value = window.location.pathname + window.location.search;
    }
    setStatus("Feedback sent. Thank you.", "is-success");
    window.setTimeout(closeModal, 900);
  }

  if (feedbackOpenButton) {
    feedbackOpenButton.addEventListener("click", openModal);
  }

  document.querySelectorAll('[data-close-modal="feedback-modal"]').forEach((button) => {
    button.addEventListener("click", closeModal);
  });

  if (feedbackForm) {
    feedbackForm.addEventListener("submit", function (event) {
      submitFeedback(event).catch(function () {
        setStatus("Unable to send feedback.", "is-error");
      });
    });
  }
})();
