/**
 * Export / import full backup (JSON) with merge or replace.
 */
(function () {
  /**
   * @param {object} state
   */
  function buildExport(state) {
    return {
      version: 3,
      exportedAt: new Date().toISOString(),
      app: "gsps-serp-pro",
      state: JSON.parse(JSON.stringify(state)),
    };
  }

  /**
   * @param {string} jsonStr
   * @param {"merge"|"replace"} mode
   * @param {object} currentState
   */
  function parseImport(jsonStr, mode, currentState) {
    const data = JSON.parse(jsonStr);
    if (!data || data.app !== "gsps-serp-pro" || !data.state) {
      throw new Error("Invalid backup file.");
    }
    if (mode === "replace") {
      return globalThis.GspsState.normalizeDay(data.state);
    }
    const cur = JSON.parse(JSON.stringify(currentState));
    const inc = data.state;
    cur.profile = Object.assign(cur.profile, inc.profile || {});
    cur.settings = Object.assign(cur.settings, inc.settings || {});
    if (Array.isArray(inc.history)) {
      const byId = new Map(cur.history.map((x) => [x.id, x]));
      for (const h of inc.history) {
        if (!h || !h.keyword) continue;
        const id = h.id || `imp_${Date.now()}_${Math.random().toString(36).slice(2, 9)}`;
        if (!byId.has(id)) {
          byId.set(id, { ...h, id });
        }
      }
      cur.history = Array.from(byId.values())
        .sort((a, b) => new Date(b.timestamp) - new Date(a.timestamp))
        .slice(0, 500);
    }
    if (inc.templates) cur.templates = inc.templates;
    if (inc.favorites) cur.favorites = Object.assign(cur.favorites || {}, inc.favorites);
    return globalThis.GspsState.normalizeDay(cur);
  }

  function download(filename, text) {
    const blob = new Blob([text], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    a.click();
    URL.revokeObjectURL(url);
  }

  globalThis.GspsBackup = {
    buildExport,
    parseImport,
    download,
  };
})();
