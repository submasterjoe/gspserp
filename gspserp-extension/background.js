/**
 * Service worker: alarms, context menus, commands, badge, queue, notifications.
 */
importScripts("js/state-manager.js", "js/offline-queue.js", "js/api-core.js");

const BADGE_COLOR = "#3B82F6";

function extractKeywordFromUrl(url, title) {
  let keyword = "";
  try {
    const u = new URL(url);
    if (u.hostname.includes("google.")) {
      keyword = new URLSearchParams(u.search).get("q") || u.searchParams.get("oq") || title || "";
    } else {
      keyword = title || u.hostname;
    }
  } catch {
    keyword = title || "";
  }
  return keyword.slice(0, 120);
}

async function refreshBadge() {
  try {
    const s = await globalThis.GspsState.load();
    globalThis.GspsState.normalizeDay(s);
    const n = String(s.usage.today || 0);
    await chrome.action.setBadgeText({ text: n.length > 3 ? "99+" : n });
    await chrome.action.setBadgeBackgroundColor({ color: BADGE_COLOR });
  } catch (_) {}
}

chrome.runtime.onInstalled.addListener(() => {
  chrome.contextMenus.removeAll(() => {
    chrome.contextMenus.create({
      id: "analyzeSelection",
      title: 'Analyze "%s" with GSPS',
      contexts: ["selection"],
    });
  });
  chrome.alarms.create("dailyReset", { periodInMinutes: 1440 });
  chrome.alarms.create("streakCheck", { periodInMinutes: 60 });
  chrome.alarms.create("tokenRefresh", { periodInMinutes: 60 });
  refreshBadge();
});

chrome.alarms.onAlarm.addListener((a) => {
  if (a.name === "dailyReset" || a.name === "streakCheck" || a.name === "tokenRefresh") {
    refreshBadge();
    if (a.name === "tokenRefresh") {
      globalThis.GspsState.load().then((s) => {
        const base = (s.settings.apiUrl || "").replace(/\/$/, "");
        if (base) globalThis.GspsApiCore.refreshIfNeeded(s, base);
      });
    }
  }
});

chrome.contextMenus.onClicked.addListener((info, tab) => {
  if (info.menuItemId === "analyzeSelection" && info.selectionText) {
    const kw = info.selectionText.trim().slice(0, 120);
    chrome.storage.local.set({ pendingAnalyze: { keyword: kw, ts: Date.now() } });
    refreshBadge();
  }
});

async function processOfflineQueue() {
  const items = await globalThis.GspsOfflineQueue.listAll();
  if (!items.length) return;
  const state = await globalThis.GspsState.load();
  let n = 0;
  for (const item of items) {
    try {
      if (item.type === "analyzeSERP") {
        await globalThis.GspsApiCore.analyzeSERP(state, item.payload.keyword, item.payload.opts || {});
      } else if (item.type === "generateContent") {
        await globalThis.GspsApiCore.generateContent(state, item.payload.keyword, item.payload.serpData);
      }
      if (item.id != null) await globalThis.GspsOfflineQueue.remove(item.id);
      n++;
    } catch (_) {}
  }
  if (n) {
    chrome.notifications.create("synced", {
      type: "basic",
      iconUrl: chrome.runtime.getURL("icons/icon128.png"),
      title: "GSPS Pro",
      message: `Synced ${n} offline ${n === 1 ? "item" : "items"}.`,
    });
  }
}

self.addEventListener("online", () => processOfflineQueue());

chrome.notifications.onClicked.addListener((id) => {
  if (id === "limit_reached") chrome.runtime.openOptionsPage();
});

chrome.commands.onCommand.addListener(async (cmd) => {
  if (cmd === "open-options") {
    chrome.runtime.openOptionsPage();
    return;
  }
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (!tab?.id) return;
  if (cmd === "analyze-serp") {
    const kw = extractKeywordFromUrl(tab.url || "", tab.title || "");
    chrome.storage.local.set({ pendingAnalyze: { keyword: kw, ts: Date.now() } });
    refreshBadge();
    return;
  }
  if (cmd === "generate-content") {
    const s = await globalThis.GspsState.load();
    const kw = s.meta.lastSearchKeyword || s.settings.defaultKeywordHint || "SEO";
    const base = (s.settings.apiUrl || "").trim();
    if (base) {
      try {
        await globalThis.GspsApiCore.generateContent(s, kw, {});
      } catch (_) {}
    }
    chrome.notifications.create({
      type: "basic",
      iconUrl: chrome.runtime.getURL("icons/icon128.png"),
      title: "GSPS Pro",
      message: base ? "Content generation requested." : "Set API URL in Options for full generation.",
    });
  }
});

chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
  if (!msg || typeof msg !== "object") return false;

  if (msg.type === "PING") {
    sendResponse({ ok: true });
    return true;
  }

  if (msg.type === "GENERATE_CONTENT") {
    (async () => {
      try {
        const state = await globalThis.GspsState.load();
        const kw = msg.keyword || state.meta.lastSearchKeyword || "SEO";
        const base = (state.settings.apiUrl || "").trim();
        if (!base) {
          const text = `Outline for “${kw}” — configure API URL in Options for live generation.`;
          sendResponse({ ok: true, text, keyword: kw });
          return;
        }
        const data = await globalThis.GspsApiCore.generateContent(state, kw, {});
        const text = data.text || data.content || JSON.stringify(data).slice(0, 500);
        sendResponse({ ok: true, text, keyword: kw });
      } catch (e) {
        sendResponse({ ok: false, error: e.message || String(e) });
      }
    })();
    return true;
  }

  if (msg.type === "TEST_API") {
    const url = (msg.url || "").trim();
    if (!url) {
      sendResponse({ ok: false, error: "No URL" });
      return true;
    }
    const ctrl = new AbortController();
    const t = setTimeout(() => ctrl.abort(), 8000);
    fetch(url, { method: "GET", signal: ctrl.signal })
      .then((r) => {
        clearTimeout(t);
        sendResponse({ ok: r.ok, status: r.status });
      })
      .catch((e) => {
        clearTimeout(t);
        sendResponse({ ok: false, error: String(e.message || e) });
      });
    return true;
  }

  if (msg.type === "REFRESH_BADGE") {
    refreshBadge();
    sendResponse({ ok: true });
    return true;
  }

  if (msg.type === "PROCESS_QUEUE") {
    processOfflineQueue().then(() => sendResponse({ ok: true }));
    return true;
  }

  return false;
});

chrome.runtime.onStartup.addListener(() => refreshBadge());
