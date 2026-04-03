/**
 * Persistent state: chrome.storage.local (syncs single device; use .sync for cross-device if desired).
 */
const STORAGE_KEY = "gspserp_v2_state";

const DEFAULTS = {
  profile: {
    displayName: "SERP Professional",
    email: "",
    avatarUrl: "", // Unsplash URL or empty → initials
    avatarMode: "initials", // 'initials' | 'url'
    timezone: Intl.DateTimeFormat().resolvedOptions().timeZone || "Asia/Kuala_Lumpur",
  },
  plan: {
    tier: "free", // 'free' | 'pro'
    label: "Free Tier",
    dailyLimit: 50,
  },
  usage: {
    dayKey: "", // YYYY-MM-DD local
    todayCount: 0,
    totalAllTime: 0,
  },
  streak: {
    count: 0,
    lastActiveDayKey: "",
  },
  preferences: {
    defaultEngine: "google",
    defaultCountry: "my",
    favoriteEngines: ["google"],
  },
  recentAnalyses: [], // { keyword, engine, ts, url? }
  theme: "light", // 'light' | 'dark'
  achievements: {
    firstSearch: false,
    searches100: false,
    nightOwl: false,
  },
};

function todayKey() {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

function loadState() {
  return new Promise((resolve) => {
    chrome.storage.local.get(STORAGE_KEY, (raw) => {
      const merged = deepMerge(JSON.parse(JSON.stringify(DEFAULTS)), raw[STORAGE_KEY] || {});
      resolve(merged);
    });
  });
}

function saveState(state) {
  return new Promise((resolve) => {
    chrome.storage.local.set({ [STORAGE_KEY]: state }, resolve);
  });
}

function deepMerge(base, patch) {
  if (!patch || typeof patch !== "object") return base;
  for (const k of Object.keys(patch)) {
    const pv = patch[k];
    const bv = base[k];
    if (
      pv &&
      typeof pv === "object" &&
      !Array.isArray(pv) &&
      bv &&
      typeof bv === "object" &&
      !Array.isArray(bv)
    ) {
      deepMerge(bv, pv);
    } else {
      base[k] = pv;
    }
  }
  return base;
}

/** Reset day counter if calendar day changed */
async function normalizeUsageDay(state) {
  const key = todayKey();
  if (state.usage.dayKey !== key) {
    state.usage.dayKey = key;
    state.usage.todayCount = 0;
  }
  return state;
}

/** After any SERP action */
async function recordUsage() {
  let state = await loadState();
  state = await normalizeUsageDay(state);
  state.usage.todayCount += 1;
  state.usage.totalAllTime += 1;
  await updateStreak(state);
  await checkAchievements(state);
  await saveState(state);
  return state;
}

async function updateStreak(state) {
  const key = todayKey();
  const y = new Date();
  y.setDate(y.getDate() - 1);
  const yKey = `${y.getFullYear()}-${String(y.getMonth() + 1).padStart(2, "0")}-${String(y.getDate()).padStart(2, "0")}`;

  if (state.streak.lastActiveDayKey === key) {
    return;
  }
  if (state.streak.lastActiveDayKey === yKey) {
    state.streak.count += 1;
  } else if (state.streak.lastActiveDayKey !== key) {
    state.streak.count = 1;
  }
  state.streak.lastActiveDayKey = key;
}

async function checkAchievements(state) {
  if (state.usage.totalAllTime >= 1) state.achievements.firstSearch = true;
  if (state.usage.totalAllTime >= 100) state.achievements.searches100 = true;
  const h = new Date().getHours();
  if (h >= 23 || h < 5) state.achievements.nightOwl = true;
}

async function pushRecentAnalysis(entry) {
  let state = await loadState();
  state.recentAnalyses = [
    { keyword: entry.keyword, engine: entry.engine || state.preferences.defaultEngine, ts: Date.now(), url: entry.url || "" },
    ...state.recentAnalyses.filter((x) => x.keyword !== entry.keyword || x.ts !== entry.ts),
  ].slice(0, 20);
  await saveState(state);
  return state;
}

// Export for non-module scripts
globalThis.GspsStorage = {
  loadState,
  saveState,
  normalizeUsageDay,
  recordUsage,
  pushRecentAnalysis,
  todayKey,
  DEFAULTS,
};
