const navToggle = document.querySelector(".nav-toggle");
const appSidebar = document.querySelector("#app-sidebar");

if (navToggle && appSidebar) {
  navToggle.addEventListener("click", () => {
    const isOpen = navToggle.getAttribute("aria-expanded") === "true";
    navToggle.setAttribute("aria-expanded", String(!isOpen));
    appSidebar.classList.toggle("sidebar-open", !isOpen);
    navToggle.setAttribute("aria-label", isOpen ? "Open navigation" : "Close navigation");
  });
  document.addEventListener("click", (event) => {
    if (
      appSidebar.classList.contains("sidebar-open")
      && !appSidebar.contains(event.target)
      && !navToggle.contains(event.target)
    ) {
      appSidebar.classList.remove("sidebar-open");
      navToggle.setAttribute("aria-expanded", "false");
      navToggle.setAttribute("aria-label", "Open navigation");
    }
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && appSidebar.classList.contains("sidebar-open")) {
      appSidebar.classList.remove("sidebar-open");
      navToggle.setAttribute("aria-expanded", "false");
      navToggle.setAttribute("aria-label", "Open navigation");
      navToggle.focus();
    }
  });
}

const assistantLanguage = document.querySelector("#assistant-language");
const languageKey = "jeevansetu-assistant-language";
const supportedLanguages = new Set(["en", "hi", "mr"]);
let savedLanguage = "en";
try {
  savedLanguage = window.localStorage.getItem(languageKey) || "en";
} catch (error) {
  console.warn("JeevanSetu could not read the saved assistant language preference.", error);
}
if (assistantLanguage) {
  if (supportedLanguages.has(savedLanguage)) assistantLanguage.value = savedLanguage;
  const syncAssistantLanguage = () => {
    document.querySelectorAll('.ai-chat-form select[name="language"]').forEach((select) => {
      select.value = assistantLanguage.value;
    });
  };
  syncAssistantLanguage();
  assistantLanguage.addEventListener("change", () => {
    try {
      window.localStorage.setItem(languageKey, assistantLanguage.value);
    } catch (error) {
      console.warn("JeevanSetu could not save the assistant language preference.", error);
    }
    syncAssistantLanguage();
  });
}

let installPromptEvent = null;
const installAppButton = document.querySelector("[data-pwa-install]");
window.addEventListener("beforeinstallprompt", (event) => {
  event.preventDefault();
  installPromptEvent = event;
  if (installAppButton) installAppButton.hidden = false;
});
window.addEventListener("appinstalled", () => {
  installPromptEvent = null;
  if (installAppButton) installAppButton.hidden = true;
});
installAppButton?.addEventListener("click", async () => {
  if (!installPromptEvent) return;
  installPromptEvent.prompt();
  await installPromptEvent.userChoice;
  installPromptEvent = null;
  installAppButton.hidden = true;
});

if ("serviceWorker" in navigator) {
  navigator.serviceWorker.register("/service-worker.js")
    .catch((error) => console.error("JeevanSetu offline support could not start.", error));
}

document.querySelectorAll("[data-resend-seconds]").forEach((button) => {
  let seconds = Number.parseInt(button.dataset.resendSeconds || "0", 10);
  const status = button.parentElement?.querySelector("[data-resend-countdown]");
  if (!Number.isFinite(seconds) || seconds <= 0) {
    button.disabled = false;
    return;
  }
  const timer = window.setInterval(() => {
    seconds -= 1;
    if (seconds <= 0) {
      window.clearInterval(timer);
      button.disabled = false;
      if (status) status.textContent = "You can request another SMS code now.";
    } else if (status) {
      status.textContent = `${seconds} seconds before resend.`;
    }
  }, 1000);
});

const assistantLauncher = document.querySelector(".ai-chat-launcher");
const assistantPanel = document.querySelector("#ai-chat-panel");

if (assistantLauncher && assistantPanel) {
  const closeButton = assistantPanel.querySelector(".ai-chat-close");
  assistantLauncher.addEventListener("click", () => {
    const shouldOpen = assistantPanel.hidden;
    assistantPanel.hidden = !shouldOpen;
    assistantLauncher.setAttribute("aria-expanded", String(shouldOpen));
    if (shouldOpen) assistantPanel.querySelector("textarea")?.focus();
  });
  closeButton?.addEventListener("click", () => {
    assistantPanel.hidden = true;
    assistantLauncher.setAttribute("aria-expanded", "false");
    assistantLauncher.focus();
  });
}

document.querySelectorAll(".ai-chat-form").forEach((form) => {
  const topicField = form.elements.namedItem("topic");
  const updateDirectoryFilters = () => {
    form.classList.toggle("has-hospital-topic", topicField?.value === "hospital");
  };
  topicField?.addEventListener("change", updateDirectoryFilters);
  updateDirectoryFilters();

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const shell = form.closest(".ai-chat-panel, .ai-page-chat");
    const messages = shell?.querySelector(".ai-chat-messages");
    const status = messages?.querySelector(".ai-chat-status");
    const sendButton = form.querySelector(".ai-chat-send");
    const messageField = form.elements.namedItem("message");
    if (!messages || !status || !sendButton || !messageField) return;

    const message = messageField.value.trim();
    const hasReport = Boolean(form.elements.namedItem("report")?.files?.length);
    if (!message && !hasReport) {
      status.textContent = "Enter a question or attach a report.";
      return;
    }

    const addBubble = (text, role) => {
      const bubble = document.createElement("p");
      bubble.className = `ai-chat-bubble ai-chat-${role}`;
      bubble.textContent = text;
      messages.insertBefore(bubble, status);
      bubble.scrollIntoView({ block: "nearest" });
    };

    addBubble(message || "Please explain my attached report.", "user");
    const pending = document.createElement("p");
    pending.className = "ai-chat-bubble ai-chat-assistant ai-chat-pending";
    pending.textContent = "Thinking…";
    messages.insertBefore(pending, status);
    status.textContent = "";
    sendButton.disabled = true;
    sendButton.classList.add("is-loading");

    try {
      const response = await fetch(form.action, {
        method: "POST",
        body: new FormData(form),
        headers: { Accept: "application/json" },
        credentials: "same-origin",
      });
      const result = await response.json();
      pending.remove();
      if (!response.ok) {
        status.textContent = result.error || "The assistant request failed. Please try again.";
      } else {
        addBubble(result.response, "assistant");
        if (result.disclaimer) status.textContent = result.disclaimer;
      }
    } catch (error) {
      pending.remove();
      status.textContent = "Could not reach the assistant service. Check your connection and try again.";
    } finally {
      sendButton.disabled = false;
      sendButton.classList.remove("is-loading");
      if (!hasReport) messageField.value = "";
      messageField.focus();
    }
  });
});
