/**
 * History CRUD, max 500 entries, analytics side-effects, export helpers.
 */
(function () {
  const MAX = 500;

  function id() {
    return `h_${Date.now()}_${Math.random().toString(36).slice(2, 10)}`;
  }

  /**
   * @param {object} state
   * @param {object} entry
   */
  function addEntry(state, entry) {
    const row = {
      id: entry.id || id(),
      keyword: (entry.keyword || "").slice(0, 200),
      timestamp: entry.timestamp || new Date().toISOString(),
      resultsCount: entry.resultsCount != null ? entry.resultsCount : 0,
      country: entry.country || state.settings.defaultCountry,
      language: entry.language || state.settings.language,
      device: entry.device || state.settings.device,
      analysisTimeMs: entry.analysisTimeMs || 0,
      success: entry.success !== false,
      errorMessage: entry.errorMessage || null,
      serpData: entry.serpData && typeof entry.serpData === "object" ? entry.serpData : {},
      favorite: !!entry.favorite,
    };
    state.history = [row, ...state.history.filter((x) => x.id !== row.id)].slice(0, MAX);
    if (!state.analytics.keywordCounts) state.analytics.keywordCounts = {};
    if (!state.analytics.dailyUsage) state.analytics.dailyUsage = {};
    if (!Array.isArray(state.analytics.hourlyHeatmap) || state.analytics.hourlyHeatmap.length !== 24) {
      state.analytics.hourlyHeatmap = new Array(24).fill(0);
    }
    if (!Array.isArray(state.analytics.weekdayHeatmap) || state.analytics.weekdayHeatmap.length !== 7) {
      state.analytics.weekdayHeatmap = new Array(7).fill(0);
    }
    const ts = new Date(row.timestamp).getTime();
    const k = row.keyword.toLowerCase();
    state.analytics.keywordCounts[k] = (state.analytics.keywordCounts[k] || 0) + 1;
    const d = row.timestamp.slice(0, 10);
    state.analytics.dailyUsage[d] = (state.analytics.dailyUsage[d] || 0) + 1;
    const hour = new Date(ts).getHours();
    state.analytics.hourlyHeatmap[hour] = (state.analytics.hourlyHeatmap[hour] || 0) + 1;
    const wd = new Date(ts).getDay();
    state.analytics.weekdayHeatmap[wd] = (state.analytics.weekdayHeatmap[wd] || 0) + 1;
    if (row.success) state.analytics.successCount++;
    else state.analytics.failCount++;
    state.meta.lastSearchKeyword = row.keyword;
    return state;
  }

  /**
   * @param {object[]} list
   * @param {string} format csv|json
   */
  function exportData(list, format) {
    if (format === "json") {
      return JSON.stringify({ version: 3, exportedAt: new Date().toISOString(), items: list }, null, 2);
    }
    const headers = [
      "id",
      "keyword",
      "timestamp",
      "resultsCount",
      "country",
      "language",
      "device",
      "analysisTimeMs",
      "success",
      "errorMessage",
    ];
    const lines = [headers.join(",")];
    for (const r of list) {
      lines.push(
        headers
          .map((h) => {
            const v = r[h];
            if (v == null) return "";
            const s = String(v).replace(/"/g, '""');
            return `"${s}"`;
          })
          .join(",")
      );
    }
    return lines.join("\n");
  }

  /**
   * @param {object} state
   * @param {string} id
   */
  function toggleFavorite(state, id) {
    const row = state.history.find((h) => h.id === id);
    if (row) row.favorite = !row.favorite;
    return state;
  }

  globalThis.GspsHistory = {
    addEntry,
    exportData,
    toggleFavorite,
    MAX,
  };
})();
