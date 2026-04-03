/**
 * Service worker — message hub for SERP / content / API test. Storage in storage.js.
 */
chrome.runtime.onInstalled.addListener(() => {
  console.info("GSPS Pro extension installed");
});

chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
  if (!msg || typeof msg !== "object") return false;

  if (msg.type === "PING") {
    sendResponse({ ok: true });
    return true;
  }

  if (msg.type === "GENERATE_CONTENT") {
    const text = `Outline: competitive SERP angles for your niche — ${new Date().toISOString().slice(0, 10)}`;
    sendResponse({ ok: true, text, keyword: "content-draft" });
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

  return false;
});
