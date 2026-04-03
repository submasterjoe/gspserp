/**
 * chrome.storage.local — canonical shape + migration from gspserp_v2_state.
 * @see popup.js / options.js
 */
(function () {
  const KEY = "gspserp_state";
  const LEGACY_KEY = "gspserp_v2_state";

  const DEFAULTS = {
    profile: {
      name: "SERP Pro",
      email: "",
      avatar: null,
      streak: 3,
    },
    settings: {
      theme: "system", // light | dark | system
      accent: "purple", // blue | purple | pink | green
      defaultCountry: "US",
      language: "en",
      device: "desktop", // desktop | mobile
      cacheTtl: 3600,
      fontSize: "medium", // small | medium | large
      apiUrl: "",
      apiKey: "",
      defaultKeywordHint: "",
    },
    usage: {
      today: 8,
      limit: 50,
      lastReset: null,
      totalAllTime: 0,
    },
    history: [], // { query, ts, engine? } max 10
  };

  function todayKey() {
    const d = new Date();
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
  }

  function deepFill(base, patch) {
    const out = JSON.parse(JSON.stringify(base));
    if (!patch || typeof patch !== "object") return out;
    for (const k of Object.keys(patch)) {
      if (patch[k] && typeof patch[k] === "object" && !Array.isArray(patch[k]) && out[k] && typeof out[k] === "object" && !Array.isArray(out[k])) {
        Object.assign(out[k], patch[k]);
      } else {
        out[k] = patch[k];
      }
    }
    return out;
  }

  function migrateV2(old) {
    const h = (old.recentAnalyses || []).map((x) => ({
      query: x.keyword || "",
      ts: x.ts || Date.now(),
      engine: x.engine || "google",
    }));
    return {
      profile: {
        name: old.profile?.displayName || DEFAULTS.profile.name,
        email: old.profile?.email || "",
        avatar: old.profile?.avatarUrl || old.profile?.avatar || null,
        streak: old.streak?.count ?? DEFAULTS.profile.streak,
      },
      settings: {
        theme: old.theme === "dark" ? "dark" : old.theme === "light" ? "light" : "system",
        accent: DEFAULTS.settings.accent,
        defaultCountry: (old.preferences?.defaultCountry || "US").toUpperCase(),
        language: DEFAULTS.settings.language,
        device: DEFAULTS.settings.device,
        cacheTtl: DEFAULTS.settings.cacheTtl,
        fontSize: DEFAULTS.settings.fontSize,
        apiUrl: DEFAULTS.settings.apiUrl,
        apiKey: DEFAULTS.settings.apiKey,
        defaultKeywordHint: "",
      },
      usage: {
        today: old.usage?.todayCount ?? DEFAULTS.usage.today,
        limit: old.plan?.dailyLimit ?? DEFAULTS.usage.limit,
        lastReset: old.usage?.dayKey || todayKey(),
        totalAllTime: old.usage?.totalAllTime ?? 0,
      },
      history: h.slice(0, 10),
    };
  }

  function normalizeUsageDay(state) {
    const key = todayKey();
    if (state.usage.lastReset !== key) {
      state.usage.today = 0;
      state.usage.lastReset = key;
    }
    return state;
  }

  function loadState() {
    return new Promise((resolve) => {
      chrome.storage.local.get([KEY, LEGACY_KEY], (raw) => {
        if (chrome.runtime.lastError) {
          resolve(deepFill(DEFAULTS, {}));
          return;
        }
        if (raw[KEY]) {
          resolve(normalizeUsageDay(deepFill(DEFAULTS, raw[KEY])));
          return;
        }
        if (raw[LEGACY_KEY]) {
          const migrated = normalizeUsageDay(deepFill(DEFAULTS, migrateV2(raw[LEGACY_KEY])));
          chrome.storage.local.set({ [KEY]: migrated }, () => {
            chrome.storage.local.remove(LEGACY_KEY, () => resolve(migrated));
          });
          return;
        }
        const fresh = deepFill(DEFAULTS, {});
        fresh.usage.lastReset = todayKey();
        resolve(normalizeUsageDay(fresh));
      });
    });
  }

  function saveState(state) {
    return new Promise((resolve) => {
      chrome.storage.local.set({ [KEY]: state }, () => resolve());
    });
  }

  function pushHistory(state, entry) {
    const q = (entry.query || entry.keyword || "").slice(0, 200);
    const row = { query: q, ts: entry.ts || Date.now(), engine: entry.engine || "google" };
    state.history = [row, ...state.history.filter((x) => x.query !== q)].slice(0, 10);
    return state;
  }

  function appendAnalysisResult(state, result) {
    normalizeUsageDay(state);
    state.usage.today = (state.usage.today || 0) + 1;
    state.usage.totalAllTime = (state.usage.totalAllTime || 0) + 1;
    pushHistory(state, {
      query: result.keyword || result.query || "",
      ts: Date.now(),
      engine: result.engine || "google",
    });
    return state;
  }

  function appendContentResult(state, text) {
    normalizeUsageDay(state);
    state.usage.today = (state.usage.today || 0) + 1;
    state.usage.totalAllTime = (state.usage.totalAllTime || 0) + 1;
    pushHistory(state, { query: (text || "Generated content").slice(0, 200), ts: Date.now(), engine: "content" });
    return state;
  }

  async function recordUsage() {
    const state = await loadState();
    state.usage.today = (state.usage.today || 0) + 1;
    state.usage.totalAllTime = (state.usage.totalAllTime || 0) + 1;
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
    DEFAULTS,
    KEY,
  };
})();
