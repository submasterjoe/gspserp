/**
 * GSPS Pro options — GspsStore + tabs + toasts
 */
(function () {
  const $ = (id) => document.getElementById(id);

  const COUNTRIES = [
    { v: "US", t: "United States" },
    { v: "GB", t: "United Kingdom" },
    { v: "MY", t: "Malaysia" },
    { v: "SG", t: "Singapore" },
    { v: "AU", t: "Australia" },
    { v: "IN", t: "India" },
    { v: "DE", t: "Germany" },
    { v: "FR", t: "France" },
    { v: "JP", t: "Japan" },
    { v: "CA", t: "Canada" },
  ];

  const LANGS = [
    { v: "en", t: "English" },
    { v: "ms", t: "Malay" },
    { v: "id", t: "Indonesian" },
    { v: "zh", t: "Chinese" },
    { v: "ja", t: "Japanese" },
    { v: "de", t: "German" },
    { v: "fr", t: "French" },
    { v: "es", t: "Spanish" },
  ];

  const FONT_KEYS = ["small", "medium", "large"];

  let pendingAvatarDataUrl = null;

  function toast(msg, ok) {
    const host = $("toastHost");
    const el = document.createElement("div");
    el.className = "toast" + (ok ? " ok" : " err");
    el.textContent = msg;
    host.appendChild(el);
    setTimeout(() => {
      el.style.opacity = "0";
      el.style.transform = "translateX(8px)";
      el.style.transition = "0.25s ease";
      setTimeout(() => el.remove(), 260);
    }, 3000);
  }

  function initials(name) {
    const t = (name || "").trim();
    if (!t || t === "SERP Pro") return "JD";
    const p = t.split(/\s+/).slice(0, 2);
    return p.map((x) => x[0].toUpperCase()).join("") || "JD";
  }

  function greetingForHour(name) {
    const h = new Date().getHours();
    let part = "Good morning";
    if (h >= 12 && h < 17) part = "Good afternoon";
    else if (h >= 17) part = "Good evening";
    const n = (name || "there").trim();
    return `${part}, ${n}`;
  }

  function resolvedDark(settings) {
    if (settings.theme === "dark") return true;
    if (settings.theme === "light") return false;
    return window.matchMedia("(prefers-color-scheme: dark)").matches;
  }

  function applyShell(state) {
    const dark = resolvedDark(state.settings);
    document.body.classList.toggle("dark-mode", dark);
    document.documentElement.setAttribute("data-accent", state.settings.accent || "purple");
    document.documentElement.classList.remove("fs-small", "fs-medium", "fs-large");
    document.documentElement.classList.add("fs-" + (state.settings.fontSize || "medium"));
    document.querySelectorAll(".accent-chip").forEach((c) => {
      c.classList.toggle("active", c.getAttribute("data-accent") === state.settings.accent);
    });
  }

  function renderAvatarBox(el, name, avatarDataUrl) {
    if (!el) return;
    const ini = initials(name);
    if (avatarDataUrl && avatarDataUrl !== "__clear__") {
      el.innerHTML = `<img src="${String(avatarDataUrl).replace(/"/g, "")}" alt="" />`;
    } else {
      el.innerHTML = `<span>${ini}</span>`;
    }
  }

  function showPage(name) {
    document.querySelectorAll(".page-panel").forEach((p) => p.classList.remove("active"));
    document.querySelectorAll(".nav-btn").forEach((l) => l.classList.remove("active"));
    const panel = $("page-" + name);
    if (panel) panel.classList.add("active");
    const link = document.querySelector('.nav-btn[data-page="' + name + '"]');
    if (link) link.classList.add("active");
  }

  document.querySelectorAll(".nav-btn").forEach((btn) => {
    btn.addEventListener("click", () => showPage(btn.getAttribute("data-page")));
  });

  function buildChart() {
    const wrap = $("usageChart");
    const labels = $("chartLabels");
    wrap.innerHTML = "";
    labels.innerHTML = "";
    const mockHeights = [38, 52, 44, 61, 48, 72, 55];
    const days = ["M", "T", "W", "T", "F", "S", "S"];
    mockHeights.forEach((h) => {
      const b = document.createElement("div");
      b.className = "chart-bar";
      b.style.height = h + "%";
      wrap.appendChild(b);
    });
    days.forEach((d) => {
      const s = document.createElement("div");
      s.textContent = d;
      labels.appendChild(s);
    });
  }

  function fillSelect(sel, items) {
    sel.innerHTML = "";
    for (const it of items) {
      const o = document.createElement("option");
      o.value = it.v;
      o.textContent = it.t;
      sel.appendChild(o);
    }
  }

  async function loadAll() {
    let state = await GspsStore.loadState();
    state = GspsStore.normalizeUsageDay(state);
    await GspsStore.saveState(state);
    pendingAvatarDataUrl = null;

    applyShell(state);

    $("dashGreeting").textContent = greetingForHour(state.profile.name);
    $("dashName").textContent = state.profile.name;
    $("dashStreak").textContent = `🔥 ${state.profile.streak || 0} day streak`;
    $("dashUsage").textContent = `${state.usage.today || 0}/${state.usage.limit || 50}`;
    $("statTotal").textContent = String(state.usage.totalAllTime || 0);
    $("statHistory").textContent = String((state.history || []).length);

    renderAvatarBox($("dashAvatarInner"), state.profile.name, state.profile.avatar);

    $("f_name").value = state.profile.name;
    $("f_email").value = state.profile.email || "";
    $("f_keyword_hint").value = state.settings.defaultKeywordHint || "";
    renderAvatarBox($("profileAvatarPrev"), state.profile.name, state.profile.avatar);

    fillSelect($("f_country"), COUNTRIES);
    $("f_country").value = (state.settings.defaultCountry || "US").toUpperCase();
    fillSelect($("f_language"), LANGS);
    $("f_language").value = state.settings.language || "en";
    $("f_device").value = state.settings.device === "mobile" ? "mobile" : "desktop";
    $("f_cache_ttl").value = String(state.settings.cacheTtl || 3600);
    $("ttlLabel").textContent = String(state.settings.cacheTtl || 3600);

    $("f_api_url").value = state.settings.apiUrl || "";
    $("f_api_key").value = state.settings.apiKey || "";
    $("f_api_key").type = "password";

    const theme = state.settings.theme || "system";
    document.querySelectorAll('input[name="theme"]').forEach((r) => {
      r.checked = r.value === theme;
    });

    const fs = FONT_KEYS.indexOf(state.settings.fontSize || "medium");
    $("f_font_size").value = String(fs >= 0 ? fs : 1);
    $("fontLabel").textContent = (state.settings.fontSize || "medium").replace(/^./, (c) => c.toUpperCase());

    buildChart();
    $("mockKw").textContent = String(12 + (state.history || []).length);
  }

  $("btnSaveProfile").addEventListener("click", async () => {
    const state = await GspsStore.loadState();
    state.profile.name = $("f_name").value.trim() || "SERP Pro";
    state.profile.email = $("f_email").value.trim();
    state.settings.defaultKeywordHint = $("f_keyword_hint").value.trim();
    if (pendingAvatarDataUrl === "__clear__") {
      state.profile.avatar = null;
      pendingAvatarDataUrl = null;
    } else if (pendingAvatarDataUrl) {
      state.profile.avatar = pendingAvatarDataUrl;
      pendingAvatarDataUrl = null;
    }
    await GspsStore.saveState(state);
    toast("Profile saved.", true);
    await loadAll();
  });

  $("btnPickAvatar").addEventListener("click", () => $("f_avatar_file").click());
  $("f_avatar_file").addEventListener("change", () => {
    const f = $("f_avatar_file").files && $("f_avatar_file").files[0];
    if (!f) return;
    const r = new FileReader();
    r.onload = () => {
      pendingAvatarDataUrl = r.result;
      renderAvatarBox($("profileAvatarPrev"), $("f_name").value || "SERP Pro", pendingAvatarDataUrl);
    };
    r.readAsDataURL(f);
  });
  $("btnClearAvatar").addEventListener("click", () => {
    pendingAvatarDataUrl = "__clear__";
    $("f_avatar_file").value = "";
    renderAvatarBox($("profileAvatarPrev"), $("f_name").value || "SERP Pro", null);
    toast("Initials shown — save profile to clear stored avatar.", true);
  });

  $("btnSaveSerp").addEventListener("click", async () => {
    const state = await GspsStore.loadState();
    state.settings.defaultCountry = ($("f_country").value || "US").toUpperCase();
    state.settings.language = $("f_language").value;
    state.settings.device = $("f_device").value;
    state.settings.cacheTtl = parseInt($("f_cache_ttl").value, 10) || 3600;
    await GspsStore.saveState(state);
    toast("SERP settings saved.", true);
    await loadAll();
  });

  $("f_cache_ttl").addEventListener("input", () => {
    $("ttlLabel").textContent = $("f_cache_ttl").value;
  });

  $("f_font_size").addEventListener("input", () => {
    const i = parseInt($("f_font_size").value, 10);
    $("fontLabel").textContent = FONT_KEYS[i] ? FONT_KEYS[i].replace(/^./, (c) => c.toUpperCase()) : "Medium";
  });

  $("btnSaveApi").addEventListener("click", async () => {
    const state = await GspsStore.loadState();
    state.settings.apiUrl = $("f_api_url").value.trim();
    state.settings.apiKey = $("f_api_key").value;
    await GspsStore.saveState(state);
    toast("API credentials saved.", true);
  });

  $("btnToggleKey").addEventListener("click", () => {
    const inp = $("f_api_key");
    const show = inp.type === "password";
    inp.type = show ? "text" : "password";
    $("btnToggleKey").textContent = show ? "Hide" : "Show";
  });

  $("btnTestApi").addEventListener("click", () => {
    const url = $("f_api_url").value.trim();
    if (!url) {
      toast("Enter an API URL first.", false);
      return;
    }
    const btn = $("btnTestApi");
    btn.classList.add("skeleton-loading");
    chrome.runtime.sendMessage({ type: "TEST_API", url }, (r) => {
      btn.classList.remove("skeleton-loading");
      if (chrome.runtime.lastError) {
        toast("Test failed: " + chrome.runtime.lastError.message, false);
        return;
      }
      if (r && r.ok) toast(`Connection OK (${r.status ?? "—"}).`, true);
      else toast("Connection issue: " + (r && r.error ? r.error : "unknown"), false);
    });
  });

  $("btnSaveAppearance").addEventListener("click", async () => {
    const state = await GspsStore.loadState();
    const th = document.querySelector('input[name="theme"]:checked');
    state.settings.theme = th ? th.value : "system";
    const activeChip = document.querySelector(".accent-chip.active");
    if (activeChip) state.settings.accent = activeChip.getAttribute("data-accent");
    const fi = parseInt($("f_font_size").value, 10);
    state.settings.fontSize = FONT_KEYS[fi] || "medium";
    await GspsStore.saveState(state);
    applyShell(state);
    toast("Appearance saved.", true);
  });

  document.querySelectorAll(".accent-chip").forEach((chip) => {
    chip.addEventListener("click", () => {
      document.querySelectorAll(".accent-chip").forEach((c) => c.classList.remove("active"));
      chip.classList.add("active");
      document.documentElement.setAttribute("data-accent", chip.getAttribute("data-accent"));
    });
  });

  $("btnQuickSerp").addEventListener("click", async () => {
    let state = await GspsStore.loadState();
    const kw = (state.settings.defaultKeywordHint || "best SEO tools").trim();
    try {
      const r = await GspsSerp.analyzeKeyword(kw);
      state = GspsStore.appendAnalysisResult(state, r);
      await GspsStore.saveState(state);
      toast(`Test SERP: ${r.keyword}`, true);
      await loadAll();
    } catch (e) {
      console.error(e);
      toast("Test SERP failed.", false);
    }
  });

  $("btnClearCache").addEventListener("click", async () => {
    await GspsStore.clearHistory();
    toast("Recent activity cleared.", true);
    await loadAll();
  });

  window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", async () => {
    const state = await GspsStore.loadState();
    if (state.settings.theme === "system") applyShell(state);
  });

  loadAll();
})();
