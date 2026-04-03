/**
 * Centralized application state (v3) with migration from gspserp_state / v2.
 * @fileoverview Persists to chrome.storage.local under key gspserp_v3_state.
 */
(function () {
  const KEY = "gspserp_v3_state";
  const LEGACY_FLAT = "gspserp_state";
  const LEGACY_V2 = "gspserp_v2_state";

  /**
   * @returns {string} Local calendar day key YYYY-MM-DD
   */
  function todayKey() {
    const d = new Date();
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
  }

  /** @returns {object} Root state object (v3) */
  function defaultState() {
    const now = new Date().toISOString();
    return {
      version: 3,
      profile: {
        name: "SERP Professional",
        email: "",
        avatar: null,
        avatarColor: 2,
        joinDate: now,
        streak: {
          current: 0,
          longest: 0,
          lastUsed: null,
        },
        achievements: [],
        preferences: {
          dailyLimit: 50,
          defaultCountry: "US",
          defaultLanguage: "en",
          defaultDevice: "desktop",
        },
      },
      settings: {
        theme: "system",
        accent: "purple",
        defaultCountry: "US",
        language: "en",
        device: "desktop",
        cacheTtl: 3600,
        fontSize: "medium",
        apiUrl: "http://localhost:5000/api/v1",
        apiKey: "",
        jwtAccess: "",
        jwtRefresh: "",
        jwtExpiresAt: 0,
        defaultKeywordHint: "",
      },
      usage: {
        today: 0,
        limit: 50,
        dayKey: todayKey(),
        totalAllTime: 0,
        byType: { serp: 0, content: 0, api: 0 },
        successfulApiCalls: 0,
        failedApiCalls: 0,
        alertsSent: { p80: false, p100: false },
      },
      history: [],
      templates: [
        { id: "tpl_meta", name: "SEO Meta Description", body: "Write a 155-char meta description for: " },
        { id: "tpl_intro", name: "Blog Intro", body: "Write an engaging intro paragraph for: " },
      ],
      favorites: {},
      drafts: { content: "" },
      analytics: {
        dailyUsage: {},
        hourlyHeatmap: new Array(24).fill(0),
        weekdayHeatmap: new Array(7).fill(0),
        keywordCounts: {},
        successCount: 0,
        failCount: 0,
      },
      meta: {
        nightOwlSearches: 0,
        weekendSearches: 0,
        batchKeywordsProcessed: 0,
        totalBatchEver: 0,
        maxBatchOnce: 0,
        lastSearchKeyword: "",
      },
    };
  }

  function deepMerge(base, patch) {
    const out = JSON.parse(JSON.stringify(base));
    if (!patch || typeof patch !== "object") return out;
    for (const k of Object.keys(patch)) {
      const pv = patch[k];
      const ov = out[k];
      if (pv && typeof pv === "object" && !Array.isArray(pv) && ov && typeof ov === "object" && !Array.isArray(ov)) {
        out[k] = deepMerge(ov, pv);
      } else {
        out[k] = pv;
      }
    }
    return out;
  }

  function mapLegacyHistoryItem(h, i) {
    const ts = typeof h.ts === "number" ? h.ts : Date.parse(h.timestamp) || Date.now();
    return {
      id: h.id || `mig_${ts}_${i}`,
      keyword: (h.keyword || h.query || "").slice(0, 200),
      timestamp: new Date(ts).toISOString(),
      resultsCount: h.resultsCount != null ? h.resultsCount : 0,
      country: h.country || "US",
      language: h.language || "en",
      device: h.device || "desktop",
      analysisTimeMs: h.analysisTimeMs != null ? h.analysisTimeMs : 0,
      success: h.success !== false,
      errorMessage: h.errorMessage || null,
      serpData: h.serpData && typeof h.serpData === "object" ? h.serpData : {},
      favorite: !!h.favorite,
    };
  }

  /**
   * Migrate flat gspserp_state (pre-v3) into v3 shape.
   * @param {object} old
   */
  function migrateFromFlat(old) {
    const d = defaultState();
    const join = old.profile?.joinDate || d.profile.joinDate;
    d.profile.name = old.profile?.name || d.profile.name;
    d.profile.email = old.profile?.email || "";
    d.profile.avatar = old.profile?.avatar || null;
    d.profile.avatarColor = typeof old.profile?.avatarColor === "number" ? old.profile.avatarColor : d.profile.avatarColor;
    d.profile.joinDate = join;
    const sc = typeof old.profile?.streak === "number" ? old.profile.streak : old.profile?.streak?.current || 0;
    d.profile.streak = {
      current: sc,
      longest: Math.max(sc, old.profile?.streak?.longest || 0),
      lastUsed: old.profile?.streak?.lastUsed || new Date().toISOString(),
    };
    d.profile.achievements = Array.isArray(old.profile?.achievements) ? old.profile.achievements : [];
    if (old.profile?.preferences) {
      d.profile.preferences = deepMerge(d.profile.preferences, old.profile.preferences);
    }
    if (old.settings) {
      d.settings = deepMerge(d.settings, old.settings);
    }
    if (!d.settings.apiUrl) d.settings.apiUrl = "http://localhost:5000/api/v1";
    if (old.usage) {
      d.usage.today = old.usage.today != null ? old.usage.today : 0;
      d.usage.limit = old.usage.limit != null ? old.usage.limit : old.profile?.preferences?.dailyLimit || 50;
      d.usage.dayKey = old.usage.lastReset || old.usage.dayKey || todayKey();
      d.usage.totalAllTime = old.usage.totalAllTime || 0;
    }
    const rawHist = Array.isArray(old.history) ? old.history : [];
    d.history = rawHist.slice(0, 500).map(mapLegacyHistoryItem);
    if (old.templates) d.templates = old.templates;
    if (old.favorites) d.favorites = old.favorites;
    if (old.drafts) d.drafts = old.drafts;
    if (old.analytics) d.analytics = deepMerge(d.analytics, old.analytics);
    if (old.meta) d.meta = deepMerge(d.meta, old.meta);
    return normalizeDay(d);
  }

  function migrateV2Payload(old) {
    const flat = {
      profile: {
        name: old.profile?.displayName || "SERP Professional",
        email: old.profile?.email || "",
        avatar: old.profile?.avatarUrl || old.profile?.avatar || null,
        streak: old.streak?.count || 0,
      },
      settings: {
        theme: old.theme === "dark" ? "dark" : old.theme === "light" ? "light" : "system",
        defaultCountry: (old.preferences?.defaultCountry || "US").toUpperCase(),
        apiUrl: "http://localhost:5000/api/v1",
      },
      usage: {
        today: old.usage?.todayCount ?? 0,
        limit: old.plan?.dailyLimit ?? 50,
        lastReset: old.usage?.dayKey || todayKey(),
        totalAllTime: old.usage?.totalAllTime ?? 0,
      },
      history: (old.recentAnalyses || []).map((x) => ({
        query: x.keyword,
        ts: x.ts || Date.now(),
        engine: x.engine || "google",
      })),
    };
    return migrateFromFlat(flat);
  }

  /**
   * Reset daily counters if calendar day changed (local timezone).
   * @param {ReturnType<defaultState>} state
   */
  function normalizeDay(state) {
    const key = todayKey();
    if (state.usage.dayKey !== key) {
      state.usage.today = 0;
      state.usage.dayKey = key;
      state.usage.alertsSent = { p80: false, p100: false };
    }
    return state;
  }

  /**
   * @returns {Promise<object>}
   */
  function load() {
    return new Promise((resolve) => {
      chrome.storage.local.get([KEY, LEGACY_FLAT, LEGACY_V2], (raw) => {
        if (chrome.runtime.lastError) {
          resolve(normalizeDay(defaultState()));
          return;
        }
        if (raw[KEY]) {
          let s = deepMerge(defaultState(), raw[KEY]);
          if (typeof s.profile.streak === "number") {
            s.profile.streak = {
              current: s.profile.streak,
              longest: s.profile.streak,
              lastUsed: null,
            };
          }
          if (!Array.isArray(s.analytics.hourlyHeatmap) || s.analytics.hourlyHeatmap.length !== 24) {
            s.analytics.hourlyHeatmap = new Array(24).fill(0);
          }
          if (!Array.isArray(s.analytics.weekdayHeatmap) || s.analytics.weekdayHeatmap.length !== 7) {
            s.analytics.weekdayHeatmap = new Array(7).fill(0);
          }
          resolve(normalizeDay(s));
          return;
        }
        if (raw[LEGACY_FLAT]) {
          const migrated = migrateFromFlat(raw[LEGACY_FLAT]);
          chrome.storage.local.set({ [KEY]: migrated }, () => resolve(migrated));
          return;
        }
        if (raw[LEGACY_V2]) {
          const migrated = migrateV2Payload(raw[LEGACY_V2]);
          chrome.storage.local.set({ [KEY]: migrated }, () => {
            chrome.storage.local.remove(LEGACY_V2, () => resolve(migrated));
          });
          return;
        }
        const fresh = normalizeDay(defaultState());
        resolve(fresh);
      });
    });
  }

  /**
   * @param {object} state
   * @returns {Promise<void>}
   */
  function save(state) {
    return new Promise((resolve, reject) => {
      try {
        state.version = 3;
        chrome.storage.local.set({ [KEY]: state }, () => {
          if (chrome.runtime.lastError) reject(chrome.runtime.lastError);
          else resolve();
        });
      } catch (e) {
        reject(e);
      }
    });
  }

  /**
   * @param {(s: ReturnType<defaultState>) => void|ReturnType<defaultState>} fn
   */
  async function patch(fn) {
    const s = await load();
    const out = fn(s);
    const next = out !== undefined ? out : s;
    await save(next);
    return next;
  }

  /**
   * Drop legacy key after successful v3 migration (optional).
   */
  async function purgeLegacyFlat() {
    return new Promise((resolve) => {
      chrome.storage.local.remove(LEGACY_FLAT, () => resolve());
    });
  }

  globalThis.GspsState = {
    load,
    save,
    patch,
    todayKey,
    defaultState,
    normalizeDay,
    KEY,
    purgeLegacyFlat,
  };
})();
