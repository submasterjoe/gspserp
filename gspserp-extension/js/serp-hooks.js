/**
 * SERP ANALYSIS HOOKS — replace internals with your real GSPS / SERP logic.
 * These functions MUST keep the same signatures so the UI keeps working.
 */

/**
 * Analyze the active browser tab (SEO/SERP context).
 * @returns {Promise<{ keyword: string, engine: string }>}
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
  return { keyword: keyword.slice(0, 120), engine: "google", url };
}

/**
 * Quick analysis from user-entered keyword
 */
async function analyzeKeyword(keyword) {
  return { keyword: keyword.trim().slice(0, 120), engine: "google", url: "" };
}

/**
 * Optional: open GSPS ERP or custom backend
 */
async function openIntegrationDashboard() {
  chrome.runtime.openOptionsPage();
}

/**
 * Content generation — uses background worker when available (preserves messaging pattern).
 * @returns {Promise<{ keyword?: string, text?: string, engine?: string }>}
 */
async function generateContent() {
  return new Promise((resolve, reject) => {
    try {
      chrome.runtime.sendMessage({ type: "GENERATE_CONTENT" }, (r) => {
        if (chrome.runtime.lastError) {
          resolve({ text: "Content draft (offline)", engine: "content" });
          return;
        }
        if (r && r.ok) {
          resolve({ text: r.text || "Generated snippet", keyword: r.keyword, engine: "content" });
        } else {
          resolve({ text: "Generated snippet", engine: "content" });
        }
      });
    } catch (e) {
      reject(e);
    }
  });
}

globalThis.GspsSerp = {
  analyzeActiveTab,
  analyzeKeyword,
  openIntegrationDashboard,
  generateContent,
};
