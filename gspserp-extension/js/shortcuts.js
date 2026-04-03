/**
 * In-page keyboard shortcuts (? help, Esc close). Command shortcuts handled in background.
 */
(function () {
  let helpEl = null;

  function removeHelp() {
    if (helpEl && helpEl.parentNode) helpEl.remove();
    helpEl = null;
  }

  function showHelp() {
    removeHelp();
    helpEl = document.createElement("div");
    helpEl.className = "gsps-shortcuts-overlay";
    helpEl.setAttribute("role", "dialog");
    helpEl.setAttribute("aria-modal", "true");
    helpEl.setAttribute("aria-label", "Keyboard shortcuts");
    helpEl.innerHTML =
      `<div class="gsps-shortcuts-panel">` +
      `<h2>Shortcuts</h2><ul>` +
      `<li><kbd>Ctrl</kbd>+<kbd>Shift</kbd>+<kbd>S</kbd> — Open popup</li>` +
      `<li><kbd>Ctrl</kbd>+<kbd>Shift</kbd>+<kbd>A</kbd> — Analyze SERP</li>` +
      `<li><kbd>Ctrl</kbd>+<kbd>Shift</kbd>+<kbd>G</kbd> — Generate content</li>` +
      `<li><kbd>Ctrl</kbd>+<kbd>Shift</kbd>+<kbd>O</kbd> — Options</li>` +
      `<li><kbd>Esc</kbd> — Close</li>` +
      `</ul>` +
      `<button type="button" class="btn-close-help">Close</button></div>`;
    document.body.appendChild(helpEl);
    helpEl.querySelector(".btn-close-help").addEventListener("click", removeHelp);
    helpEl.addEventListener("click", (e) => {
      if (e.target === helpEl) removeHelp();
    });
  }

  function init() {
    document.addEventListener(
      "keydown",
      (e) => {
        if (e.key === "?" && !e.ctrlKey && !e.metaKey) {
          const t = e.target;
          if (t && (t.tagName === "INPUT" || t.tagName === "TEXTAREA")) return;
          e.preventDefault();
          showHelp();
        }
        if (e.key === "Escape") removeHelp();
      },
      true
    );
  }

  globalThis.GspsShortcuts = { init, showHelp, removeHelp };
})();
