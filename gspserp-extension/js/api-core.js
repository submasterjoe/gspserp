/**
 * API transport: JWT, retries, timeouts (no DOM). Safe for service worker.
 */
(function () {
  const TIMEOUT_MS = 30000;
  const DEBUG = false;

  function log() {
    if (DEBUG && typeof console !== "undefined" && console.log) {
      console.log.apply(console, arguments);
    }
  }

  /**
   * @param {object} state
   * @returns {Promise<object|null>}
   */
  async function getAuthHeaders(state) {
    const h = { "Content-Type": "application/json" };
    const token = state.settings?.jwtAccess || state.settings?.apiKey;
    if (token) {
      if (state.settings.jwtAccess) {
        h.Authorization = `Bearer ${state.settings.jwtAccess}`;
      } else {
        h.Authorization = `Bearer ${state.settings.apiKey}`;
      }
    }
    return h;
  }

  /**
   * @param {object} state
   * @param {string} baseUrl
   */
  async function refreshIfNeeded(state, baseUrl) {
    const exp = state.settings.jwtExpiresAt || 0;
    const soon = Date.now() + 5 * 60 * 1000;
    if (!state.settings.jwtRefresh || exp > soon) return state;
    await fetch(`${baseUrl.replace(/\/$/, "")}/auth/refresh`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh_token: state.settings.jwtRefresh }),
    })
      .then((r) => r.json())
      .then((j) => {
        if (j.access_token) state.settings.jwtAccess = j.access_token;
        if (j.expires_in) state.settings.jwtExpiresAt = Date.now() + j.expires_in * 1000;
      })
      .catch(() => {});
    return state;
  }

  /**
   * @param {string} url
   * @param {RequestInit} init
   */
  async function fetchWithTimeout(url, init) {
    const ctrl = new AbortController();
    const t = setTimeout(() => ctrl.abort(), TIMEOUT_MS);
    try {
      const res = await fetch(url, { ...init, signal: ctrl.signal });
      clearTimeout(t);
      return res;
    } catch (e) {
      clearTimeout(t);
      throw e;
    }
  }

  /**
   * @param {object} state
   * @param {string} keyword
   * @param {object} opts
   */
  async function analyzeSERP(state, keyword, opts) {
    const base = (state.settings.apiUrl || "").replace(/\/$/, "");
    if (!base) throw new Error("NO_API_URL");
    const url = `${base}/serp/analyze`;
    await refreshIfNeeded(state, base);
    const headers = await getAuthHeaders(state);
    const body = JSON.stringify({
      keyword,
      country: opts.country || state.settings.defaultCountry,
      language: opts.language || state.settings.language,
      device: opts.device || state.settings.device,
    });
    let res = await fetchWithTimeout(url, { method: "POST", headers, body });
    if (res.status === 401 && state.settings.jwtRefresh) {
      await refreshIfNeeded(state, base);
      const h2 = await getAuthHeaders(state);
      res = await fetchWithTimeout(url, { method: "POST", headers: h2, body });
    }
    const text = await res.text();
    let data;
    try {
      data = text ? JSON.parse(text) : {};
    } catch {
      data = { raw: text };
    }
    if (!res.ok) {
      const err = new Error(data?.message || `HTTP ${res.status}`);
      err.status = res.status;
      err.body = data;
      throw err;
    }
    return data;
  }

  /**
   * @param {object} state
   * @param {string} keyword
   * @param {object} serpData
   */
  async function generateContent(state, keyword, serpData) {
    const base = (state.settings.apiUrl || "").replace(/\/$/, "");
    if (!base) throw new Error("NO_API_URL");
    const url = `${base}/content/generate`;
    await refreshIfNeeded(state, base);
    const headers = await getAuthHeaders(state);
    const body = JSON.stringify({ keyword, serp_data: serpData || {} });
    const res = await fetchWithTimeout(url, { method: "POST", headers, body });
    const text = await res.text();
    let data;
    try {
      data = text ? JSON.parse(text) : {};
    } catch {
      data = { raw: text };
    }
    if (!res.ok) {
      const err = new Error(data?.message || `HTTP ${res.status}`);
      err.status = res.status;
      err.body = data;
      throw err;
    }
    return data;
  }

  /**
   * @param {object} state
   */
  async function getUserStats(state) {
    const base = (state.settings.apiUrl || "").replace(/\/$/, "");
    if (!base) throw new Error("NO_API_URL");
    await refreshIfNeeded(state, base);
    const headers = await getAuthHeaders(state);
    const res = await fetchWithTimeout(`${base}/user/stats`, { method: "GET", headers });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data?.message || `HTTP ${res.status}`);
    return data;
  }

  /**
   * @param {object} state
   * @param {object} profileData
   */
  async function syncProfile(state, profileData) {
    const base = (state.settings.apiUrl || "").replace(/\/$/, "");
    if (!base) throw new Error("NO_API_URL");
    const headers = await getAuthHeaders(state);
    const res = await fetchWithTimeout(`${base}/user/sync`, {
      method: "POST",
      headers,
      body: JSON.stringify(profileData),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data?.message || `HTTP ${res.status}`);
    return data;
  }

  /**
   * @param {object} state
   * @param {string} key
   */
  async function validateApiKey(state, key) {
    const base = (state.settings.apiUrl || "").replace(/\/$/, "");
    if (!base) throw new Error("NO_API_URL");
    const res = await fetchWithTimeout(`${base}/auth/validate`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ api_key: key }),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data?.message || `HTTP ${res.status}`);
    return data;
  }

  globalThis.GspsApiCore = {
    analyzeSERP,
    generateContent,
    getUserStats,
    syncProfile,
    validateApiKey,
    refreshIfNeeded,
    fetchWithTimeout,
  };
})();
