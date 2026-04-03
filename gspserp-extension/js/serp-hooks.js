/**
 * SERP hooks — stable signatures; uses API when configured, else local keyword extraction.
 */

/**
 * @returns {Promise<{ keyword: string, engine: string, url?: string, local?: boolean, resultsCount?: number, serpData?: object }>}
 */
async function analyzeActiveTab() {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  const url = tab?.url || "";
  let keyword = "";
  try {
    const u = new URL(url);
    if (u.hostname.includes("google.")) {
      keyword = new URLSearchParams(u.search).get("q") || u.searchParams.get("oq") || tab.title || "";
    } else {
      keyword = tab?.title || u.hostname;
    }
  } catch {
    keyword = tab?.title || "Current page";
  }
  keyword = keyword.slice(0, 120);
  const state = await globalThis.GspsState.load();
  if (!globalThis.GspsUsage.canUse(state)) {
    const err = new Error("DAILY_LIMIT");
    err.code = "LIMIT";
    throw err;
  }
  const base = (state.settings.apiUrl || "").trim();
  if (!base) {
    return {
      keyword,
      engine: "google",
      url,
      local: true,
      resultsCount: 0,
      serpData: { note: "local" },
    };
  }
  try {
    const data = await globalThis.GspsApiClient.analyzeSERP(keyword, {
      country: state.settings.defaultCountry,
      language: state.settings.language,
      device: state.settings.device,
    });
    if (data && data.local) {
      return { keyword, engine: "google", url, local: true, resultsCount: 0, serpData: {} };
    }
    return {
      keyword,
      engine: "api",
      url,
      resultsCount: data.results_count != null ? data.results_count : data.resultsCount != null ? data.resultsCount : 0,
      serpData: data,
    };
  } catch (e) {
    return {
      keyword,
      engine: "google",
      url,
      local: true,
      resultsCount: 0,
      serpData: { error: e.message || String(e) },
    };
  }
}

/**
 * @param {string} keyword
 */
async function analyzeKeyword(keyword) {
  const state = await globalThis.GspsState.load();
  if (!globalThis.GspsUsage.canUse(state)) {
    const err = new Error("DAILY_LIMIT");
    err.code = "LIMIT";
    throw err;
  }
  const base = (state.settings.apiUrl || "").trim();
  if (!base) {
    return { keyword: keyword.trim().slice(0, 120), engine: "google", url: "", local: true };
  }
  try {
    const data = await globalThis.GspsApiClient.analyzeSERP(keyword.trim().slice(0, 120), {});
    if (data && data.local) {
      return { keyword: keyword.trim().slice(0, 120), engine: "google", url: "", local: true };
    }
    return {
      keyword: keyword.trim().slice(0, 120),
      engine: "api",
      url: "",
      resultsCount: data.results_count != null ? data.results_count : data.resultsCount,
      serpData: data,
    };
  } catch (e) {
    return { keyword: keyword.trim().slice(0, 120), engine: "google", url: "", local: true, serpData: { error: e.message } };
  }
}

async function openIntegrationDashboard() {
  chrome.runtime.openOptionsPage();
}

/**
 * @returns {Promise<{ text?: string, keyword?: string, engine?: string }>}
 */
async function generateContent() {
  const state = await globalThis.GspsState.load();
  const last = state.meta.lastSearchKeyword || state.settings.defaultKeywordHint || "SEO";
  return new Promise((resolve) => {
    chrome.runtime.sendMessage({ type: "GENERATE_CONTENT", keyword: last }, (r) => {
      if (chrome.runtime.lastError) {
        resolve({ text: "Background unavailable.", engine: "content" });
        return;
      }
      if (r && r.ok) {
        resolve({ text: r.text, keyword: r.keyword || last, engine: "content" });
      } else {
        resolve({ text: "Could not generate.", engine: "content" });
      }
    });
  });
}

globalThis.GspsSerp = {
  analyzeActiveTab,
  analyzeKeyword,
  openIntegrationDashboard,
  generateContent,
};
