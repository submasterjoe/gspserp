/**
 * Toast notifications: success, error, warning, info — stack max 3, pause on hover.
 */
(function () {
  const MAX = 3;
  let stack = [];

  function escapeHtml(s) {
    const d = document.createElement("div");
    d.textContent = s;
    return d.innerHTML;
  }

  /**
   * @param {HTMLElement} host
   * @param {string} message
   * @param {"success"|"error"|"warning"|"info"} type
   * @param {{ duration?: number, actionLabel?: string, onAction?: () => void }} [opts]
   */
  function show(host, message, type, opts) {
    opts = opts || {};
    const duration = opts.duration != null ? opts.duration : type === "error" ? 5000 : 3000;
    if (!host) return;
    while (stack.length >= MAX) {
      const old = stack.shift();
      if (old && old.el.parentNode) old.el.remove();
    }
    const el = document.createElement("div");
    el.className = "gsps-toast gsps-toast--" + type;
    el.setAttribute("role", "status");
    const icon =
      type === "success"
        ? "✓"
        : type === "error"
          ? "✕"
          : type === "warning"
            ? "⚠"
            : "ℹ";
    el.innerHTML =
      `<span class="gsps-toast__icon" aria-hidden="true">${icon}</span>` +
      `<span class="gsps-toast__msg">${escapeHtml(message)}</span>` +
      `<button type="button" class="gsps-toast__close" aria-label="Dismiss">×</button>`;
    if (opts.actionLabel && opts.onAction) {
      const ab = document.createElement("button");
      ab.type = "button";
      ab.className = "gsps-toast__action";
      ab.textContent = opts.actionLabel;
      ab.addEventListener("click", () => opts.onAction());
      el.querySelector(".gsps-toast__msg").after(ab);
    }
    host.appendChild(el);
    let left = duration;
    let timer = setTimeout(finish, left);
    const entry = { el, timer };
    stack.push(entry);

    function finish() {
      clearTimeout(timer);
      el.classList.add("gsps-toast--out");
      setTimeout(() => {
        el.remove();
        stack = stack.filter((x) => x !== entry);
      }, 280);
    }

    el.querySelector(".gsps-toast__close").addEventListener("click", finish);

    let pause = false;
    el.addEventListener("mouseenter", () => {
      pause = true;
      clearTimeout(timer);
    });
    el.addEventListener("mouseleave", () => {
      if (!pause) return;
      pause = false;
      timer = setTimeout(finish, Math.min(3000, duration));
    });
  }

  globalThis.GspsNotify = { show };
})();
