/**
 * Daily usage, limits, ring thresholds, browser notifications at 80%/100%.
 */
(function () {
  /**
   * @param {object} state
   * @param {"serp"|"content"|"api"} kind
   * @param {boolean} success
   */
  function record(state, kind, success) {
    globalThis.GspsState.normalizeDay(state);
    state.usage.today = (state.usage.today || 0) + 1;
    state.usage.totalAllTime = (state.usage.totalAllTime || 0) + 1;
    if (state.usage.byType && kind in state.usage.byType) {
      state.usage.byType[kind] = (state.usage.byType[kind] || 0) + 1;
    }
    if (success) {
      if (kind === "api") {
        state.usage.successfulApiCalls = (state.usage.successfulApiCalls || 0) + 1;
      }
    } else {
      state.usage.failedApiCalls = (state.usage.failedApiCalls || 0) + 1;
    }
    const lim = state.usage.limit || state.profile.preferences.dailyLimit || 50;
    const pct = lim ? (state.usage.today / lim) * 100 : 0;
    if (pct >= 80 && pct < 100 && !state.usage.alertsSent.p80) {
      state.usage.alertsSent.p80 = true;
      try {
        chrome.notifications.create(
          "usage80",
          {
            type: "basic",
            iconUrl: chrome.runtime.getURL("icons/icon128.png"),
            title: "GSPS Pro",
            message: "You've used 80% of today's limit.",
          },
          () => {}
        );
      } catch (_) {}
    }
    if (pct >= 100 && !state.usage.alertsSent.p100) {
      state.usage.alertsSent.p100 = true;
      try {
        chrome.notifications.create(
          "limit_reached",
          {
            type: "basic",
            iconUrl: chrome.runtime.getURL("icons/icon128.png"),
            title: "GSPS Pro",
            message: "Daily limit reached. Open options to adjust.",
          },
          () => {}
        );
      } catch (_) {}
    }
    return state;
  }

  /**
   * @param {number} used
   * @param {number} limit
   */
  function percent(used, limit) {
    if (!limit) return 0;
    return Math.min(100, (used / limit) * 100);
  }

  /**
   * @param {number} pct
   * @returns {string} CSS color
   */
  function ringColor(pct) {
    if (pct <= 60) return "#10B981";
    if (pct <= 85) return "#F59E0B";
    return "#EF4444";
  }

  /**
   * @param {object} state
   */
  function canUse(state) {
    globalThis.GspsState.normalizeDay(state);
    const lim = state.usage.limit || 50;
    return (state.usage.today || 0) < lim;
  }

  globalThis.GspsUsage = {
    record,
    percent,
    ringColor,
    canUse,
  };
})();
