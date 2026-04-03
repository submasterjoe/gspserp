/**
 * Compatibility shim: GspsStore API on top of GspsState + domain modules.
 */
(function () {
  const KEY = globalThis.GspsState ? globalThis.GspsState.KEY : "gspserp_v3_state";

  async function loadState() {
    return globalThis.GspsState.load();
  }

  async function saveState(state) {
    return globalThis.GspsState.save(state);
  }

  function normalizeUsageDay(state) {
    return globalThis.GspsState.normalizeDay(state);
  }

  function todayKey() {
    return globalThis.GspsState.todayKey();
  }

  /**
   * @param {object} state
   * @param {object} result keyword, engine, url, resultsCount?, serpData?, local?
   */
  function appendAnalysisResult(state, result) {
    const t0 = typeof performance !== "undefined" ? performance.now() : Date.now();
    globalThis.GspsState.normalizeDay(state);
    globalThis.GspsProfile.updateStreakOnActivity(state);
    const hour = new Date().getHours();
    if (hour < 5 || hour >= 23) {
      state.meta.nightOwlSearches = (state.meta.nightOwlSearches || 0) + 1;
    }
    const wd = new Date().getDay();
    if (wd === 0 || wd === 6) {
      state.meta.weekendSearches = (state.meta.weekendSearches || 0) + 1;
    }
    const usageKind = result.engine === "api" ? "api" : "serp";
    globalThis.GspsUsage.record(state, usageKind, true);
    const ms = typeof performance !== "undefined" ? performance.now() - t0 : 0;
    globalThis.GspsHistory.addEntry(state, {
      keyword: result.keyword || result.query || "",
      resultsCount: result.resultsCount != null ? result.resultsCount : 0,
      country: state.settings.defaultCountry,
      language: state.settings.language,
      device: state.settings.device,
      analysisTimeMs: ms,
      success: true,
      errorMessage: null,
      serpData: result.serpData && typeof result.serpData === "object" ? result.serpData : { engine: result.engine, url: result.url },
    });
    globalThis.GspsAchievements.evaluate(state);
    return state;
  }

  /**
   * @param {object} state
   * @param {string} text
   */
  function appendContentResult(state, text) {
    globalThis.GspsState.normalizeDay(state);
    globalThis.GspsProfile.updateStreakOnActivity(state);
    globalThis.GspsUsage.record(state, "content", true);
    globalThis.GspsHistory.addEntry(state, {
      keyword: (text || "Generated content").slice(0, 200),
      resultsCount: 0,
      analysisTimeMs: 0,
      success: true,
      serpData: { type: "content" },
    });
    globalThis.GspsAchievements.evaluate(state);
    return state;
  }

  function pushHistory(state, entry) {
    return globalThis.GspsHistory.addEntry(state, {
      keyword: entry.query || entry.keyword,
      timestamp: new Date(entry.ts || Date.now()).toISOString(),
      serpData: { engine: entry.engine },
    });
  }

  async function recordUsage() {
    const state = await loadState();
    globalThis.GspsUsage.record(state, "api", true);
    await saveState(state);
    return state;
  }

  async function clearHistory() {
    const state = await loadState();
    state.history = [];
    await saveState(state);
  }

  globalThis.GspsStore = {
    loadState,
    saveState,
    normalizeUsageDay,
    pushHistory,
    appendAnalysisResult,
    appendContentResult,
    recordUsage,
    clearHistory,
    todayKey,
    DEFAULTS: globalThis.GspsState ? globalThis.GspsState.defaultState() : {},
    KEY,
  };
})();
