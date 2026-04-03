/**
 * Global error handlers for unhandled rejections and runtime errors.
 */
(function () {
  const DEBUG = false;

  function friendly(msg) {
    if (/quota|QuotaExceededError/i.test(String(msg))) {
      return "Unable to save. Storage quota exceeded. Clear some history in Settings.";
    }
    if (/network|fetch|Failed to fetch/i.test(String(msg))) {
      return "Connection failed. Check your internet and API settings.";
    }
    return "Something went wrong. Try refreshing the extension.";
  }

  function notifyUser(text) {
    try {
      const host = document.getElementById("toastHost");
      if (host && globalThis.GspsNotify) {
        globalThis.GspsNotify.show(host, text, "error", { duration: 6000 });
      }
    } catch (_) {}
  }

  window.addEventListener("unhandledrejection", (ev) => {
    const msg = ev.reason && (ev.reason.message || ev.reason);
    if (DEBUG && typeof console !== "undefined" && console.error) console.error(ev.reason);
    notifyUser(friendly(msg));
  });

  window.addEventListener("error", (ev) => {
    if (DEBUG && typeof console !== "undefined" && console.error) console.error(ev.error);
    notifyUser(friendly(ev.message));
  });

  globalThis.GspsErrors = {
    friendly,
    notifyUser,
  };
})();
