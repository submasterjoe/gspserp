/**
 * High-level API: state-aware, toasts, offline queue, exponential backoff.
 */
(function () {
  const cache = new Map();
  const CACHE_TTL = 5 * 60 * 1000;

  function cacheKey(method, url, body) {
    return method + ":" + url + ":" + (body || "");
  }

  /**
   * @param {number} attempt 0-based
   */
  async function backoff(attempt) {
    const ms = Math.min(8000, 1000 * Math.pow(2, attempt));
    await new Promise((r) => setTimeout(r, ms));
  }

  /**
   * @param {Error} err
   * @param {object} body
   */
  function mapError(err, body) {
    const status = err.status || 0;
    if (status === 400) return body?.message || "Validation error from server.";
    if (status === 401) return "Unauthorized. Check API key or sign in again.";
    if (status === 429) return "Rate limited. Try again later.";
    if (status >= 500) return "Server error. Try again later.";
    if (err.message === "NO_API_URL") return "";
    if (err.name === "AbortError") return "Request took too long. Check your connection.";
    return "Network error. " + (err.message || "");
  }

  /**
   * @param {string} keyword
   * @param {object} opts
   */
  async function analyzeSERP(keyword, opts) {
    const state = await globalThis.GspsState.load();
    const base = (state.settings.apiUrl || "").trim();
    if (!base) {
      return { local: true, keyword: keyword.trim(), engine: "google", url: "" };
    }
    const key = cacheKey("POST", base + "/serp/analyze", keyword);
    const hit = cache.get(key);
    if (hit && Date.now() - hit.t < CACHE_TTL) return hit.data;

    let lastErr = new Error("Request failed");
    for (let i = 0; i < 3; i++) {
      try {
        if (!navigator.onLine) throw new Error("offline");
        const data = await globalThis.GspsApiCore.analyzeSERP(state, keyword, opts || {});
        cache.set(key, { t: Date.now(), data });
        return data;
      } catch (e) {
        lastErr = e;
        if (e.message === "offline" || !navigator.onLine) {
          await globalThis.GspsOfflineQueue.enqueue({ type: "analyzeSERP", payload: { keyword, opts } });
          throw new Error("Queued for sync when online.");
        }
        const st = e.status || 0;
        if (st === 401 || st === 400) break;
        if (i < 2) await backoff(i);
      }
    }
    const msg = mapError(lastErr, lastErr.body);
    throw new Error(msg || lastErr.message);
  }

  /**
   * @param {string} keyword
   * @param {object} serpData
   */
  async function generateContent(keyword, serpData) {
    const state = await globalThis.GspsState.load();
    const base = (state.settings.apiUrl || "").trim();
    if (!base) {
      return { text: "Configure API URL in Options to generate content via your backend.", local: true };
    }
    for (let i = 0; i < 3; i++) {
      try {
        if (!navigator.onLine) {
          await globalThis.GspsOfflineQueue.enqueue({ type: "generateContent", payload: { keyword, serpData } });
          throw new Error("Queued for sync when online.");
        }
        return await globalThis.GspsApiCore.generateContent(state, keyword, serpData);
      } catch (e) {
        if (e.message && e.message.indexOf("Queued") >= 0) throw e;
        if (i < 2) await backoff(i);
        else throw e;
      }
    }
    throw new Error("Generation failed after retries.");
  }

  async function getUserStats() {
    const state = await globalThis.GspsState.load();
    return globalThis.GspsApiCore.getUserStats(state);
  }

  async function syncProfile(profileData) {
    const state = await globalThis.GspsState.load();
    return globalThis.GspsApiCore.syncProfile(state, profileData);
  }

  async function validateApiKey(key) {
    const state = await globalThis.GspsState.load();
    return globalThis.GspsApiCore.validateApiKey(state, key);
  }

  globalThis.GspsApiClient = {
    analyzeSERP,
    generateContent,
    getUserStats,
    syncProfile,
    validateApiKey,
    mapError,
  };
})();
