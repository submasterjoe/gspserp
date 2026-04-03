/**
 * GSPS SERP Pro — options page (v3).
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

  let histPage = 0;
  const HIST_PAGE = 50;
  let filterDebounce = null;
  let pendingAvatar = null;
  let csvText = "";

  function toast(msg, type) {
    const host = $("toastHost");
    if (globalThis.GspsNotify && host) globalThis.GspsNotify.show(host, msg, type || "info");
  }

  function initials(name) {
    const t = (name || "").trim();
    if (!t || t === "SERP Pro") return "JD";
    return globalThis.GspsProfile.initials(name);
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

  function showPage(name) {
    document.querySelectorAll(".page-panel").forEach((p) => p.classList.remove("active"));
    document.querySelectorAll(".nav-btn").forEach((l) => l.classList.remove("active"));
    const panel = $("page-" + name);
    if (panel) panel.classList.add("active");
    const link = document.querySelector('.nav-btn[data-page="' + name + '"]');
    if (link) link.classList.add("active");
    if (name === "analytics") setTimeout(refreshCharts, 80);
  }

  document.querySelectorAll(".nav-btn").forEach((btn) => {
    btn.addEventListener("click", () => showPage(btn.getAttribute("data-page")));
  });

  function fillSelect(sel, items) {
    sel.innerHTML = "";
    for (const it of items) {
      const o = document.createElement("option");
      o.value = it.v;
      o.textContent = it.t;
      sel.appendChild(o);
    }
  }

  function renderBadges(state) {
    const row = $("badgeRow");
    if (!row) return;
    row.innerHTML = "";
    (state.profile.achievements || []).forEach((id) => {
      const s = document.createElement("span");
      s.className = "badge-pill";
      s.textContent = globalThis.GspsAchievements.label(id);
      row.appendChild(s);
    });
  }

  function renderDash(state) {
    $("dashGreeting").textContent = "Welcome back";
    $("dashName").textContent = state.profile.name;
    $("dashStreak").textContent = `🔥 ${state.profile.streak.current || 0} day streak`;
    const lim = state.usage.limit || 50;
    $("dashUsage").textContent = `${state.usage.today || 0}/${lim}`;
    const inner = $("dashAvatarInner");
    if (state.profile.avatar) {
      inner.innerHTML = `<img src="${state.profile.avatar.replace(/"/g, "")}" alt="User avatar" />`;
    } else {
      inner.innerHTML = `<span>${initials(state.profile.name)}</span>`;
    }
    renderBadges(state);
  }

  function refreshCharts() {
    const state = window.__gspsStateCache;
    if (!state) return;
    const c1 = $("chartLine");
    const c2 = $("chartBar");
    const c3 = $("chartPie");
    const c4 = $("chartHeat");
    if (c1) globalThis.GspsCharts.drawLineUsage(c1, state.analytics.dailyUsage || {});
    if (c2) globalThis.GspsCharts.drawBarKeywords(c2, state.analytics.keywordCounts || {});
    if (c3) globalThis.GspsCharts.drawPieSuccess(c3, state.analytics.successCount || 0, state.analytics.failCount || 0);
    if (c4) globalThis.GspsCharts.drawHeatmap(c4, state.analytics.hourlyHeatmap || new Array(24).fill(0));
  }

  function getFilteredHistory(state) {
    const q = ($("histFilter") && $("histFilter").value.trim().toLowerCase()) || "";
    let list = [...(state.history || [])];
    if (q) list = list.filter((h) => (h.keyword || "").toLowerCase().indexOf(q) >= 0);
    const sort = $("histSort") ? $("histSort").value : "date-desc";
    if (sort === "date-desc") list.sort((a, b) => new Date(b.timestamp) - new Date(a.timestamp));
    if (sort === "date-asc") list.sort((a, b) => new Date(a.timestamp) - new Date(b.timestamp));
    if (sort === "kw-asc") list.sort((a, b) => (a.keyword || "").localeCompare(b.keyword || ""));
    if (sort === "count-desc") list.sort((a, b) => (b.resultsCount || 0) - (a.resultsCount || 0));
    return list;
  }

  function renderHistoryTable(state) {
    const list = getFilteredHistory(state);
    const tbody = $("histBody");
    if (!tbody) return;
    tbody.innerHTML = "";
    const start = histPage * HIST_PAGE;
    const page = list.slice(start, start + HIST_PAGE);
    $("histPageLabel").textContent = `${start + 1}–${Math.min(start + page.length, list.length)} of ${list.length}`;
    page.forEach((h) => {
      const tr = document.createElement("tr");
      const star = h.favorite ? "★" : "☆";
      tr.innerHTML =
        `<td><button type="button" class="btn-icon-star" data-id="${h.id}" aria-label="Toggle favorite">${star}</button></td>` +
        `<td><button type="button" class="link-kw" data-kw="${encodeURIComponent(h.keyword)}">${escapeHtml(h.keyword)}</button></td>` +
        `<td>${escapeHtml(new Date(h.timestamp).toLocaleString())}</td>` +
        `<td>${h.resultsCount != null ? h.resultsCount : ""}</td>` +
        `<td><button type="button" class="btn-del" data-id="${h.id}" aria-label="Delete row">🗑</button></td>`;
      tbody.appendChild(tr);
    });
    tbody.querySelectorAll(".btn-icon-star").forEach((b) =>
      b.addEventListener("click", async () => {
        let st = await globalThis.GspsStore.loadState();
        globalThis.GspsHistory.toggleFavorite(st, b.getAttribute("data-id"));
        await globalThis.GspsStore.saveState(st);
        await loadAll();
      })
    );
    tbody.querySelectorAll(".link-kw").forEach((b) =>
      b.addEventListener("click", async () => {
        const kw = decodeURIComponent(b.getAttribute("data-kw"));
        await globalThis.GspsSerp.analyzeKeyword(kw);
        toast("Re-run queued for " + kw, "info");
      })
    );
    tbody.querySelectorAll(".btn-del").forEach((b) =>
      b.addEventListener("click", async () => {
        if (!confirm("Delete this entry?")) return;
        let st = await globalThis.GspsStore.loadState();
        st.history = st.history.filter((x) => x.id !== b.getAttribute("data-id"));
        await globalThis.GspsStore.saveState(st);
        await loadAll();
      })
    );
  }

  function escapeHtml(s) {
    const d = document.createElement("div");
    d.textContent = s;
    return d.innerHTML;
  }

  async function loadAll() {
    let state = await globalThis.GspsStore.loadState();
    globalThis.GspsState.normalizeDay(state);
    window.__gspsStateCache = state;
    await globalThis.GspsStore.saveState(state);
    applyShell(state);
    renderDash(state);

    $("f_name").value = state.profile.name;
    $("f_email").value = state.profile.email || "";
    $("f_keyword_hint").value = state.settings.defaultKeywordHint || "";
    $("f_daily_limit").value = state.profile.preferences.dailyLimit || state.usage.limit || 50;
    renderAvatarColor(state.profile.avatarColor || 0);
    renderProfileAvatar(state);

    fillSelect($("f_country"), COUNTRIES);
    $("f_country").value = (state.settings.defaultCountry || "US").toUpperCase();
    fillSelect($("f_language"), LANGS);
    $("f_language").value = state.settings.language || "en";
    $("f_device").value = state.settings.device === "mobile" ? "mobile" : "desktop";
    $("f_cache_ttl").value = String(state.settings.cacheTtl || 3600);
    $("ttlLabel").textContent = String(state.settings.cacheTtl || 3600);

    $("f_api_url").value = state.settings.apiUrl || "";
    $("f_api_key").value = state.settings.apiKey || "";

    const theme = state.settings.theme || "system";
    document.querySelectorAll('input[name="theme"]').forEach((r) => {
      r.checked = r.value === theme;
    });
    const fi = FONT_KEYS.indexOf(state.settings.fontSize || "medium");
    $("f_font_size").value = String(fi >= 0 ? fi : 1);
    $("fontLabel").textContent = FONT_KEYS[fi >= 0 ? fi : 1];

    renderHistoryTable(state);
    refreshCharts();
  }

  function renderAvatarColor(selected) {
    const row = $("avatarColorRow");
    if (!row) return;
    row.innerHTML = "";
    for (let i = 0; i < globalThis.GspsProfile.GRADIENTS.length; i++) {
      const b = document.createElement("button");
      b.type = "button";
      b.className = "avatar-color-swatch" + (i === selected ? " active" : "");
      b.style.background = globalThis.GspsProfile.gradientForIndex(i);
      b.setAttribute("aria-label", "Gradient " + (i + 1));
      b.addEventListener("click", () => {
        row.querySelectorAll(".avatar-color-swatch").forEach((x) => x.classList.remove("active"));
        b.classList.add("active");
        b.dataset.picked = String(i);
      });
      b.dataset.picked = String(i);
      row.appendChild(b);
    }
  }

  function renderProfileAvatar(state) {
    const el = $("profileAvatarPrev");
    if (!el) return;
    if (pendingAvatar && pendingAvatar !== "__clear__") {
      el.innerHTML = `<img src="${pendingAvatar.replace(/"/g, "")}" alt="" />`;
    } else if (state.profile.avatar) {
      el.innerHTML = `<img src="${state.profile.avatar.replace(/"/g, "")}" alt="" />`;
    } else {
      el.innerHTML = `<span>${initials(state.profile.name)}</span>`;
    }
  }

  function validateApiUrl() {
    const v = $("f_api_url").value.trim();
    const ok = !v || /^https?:\/\/.+/i.test(v);
    $("hint_url").textContent = ok ? "✓" : "Must start with http:// or https://";
    $("hint_url").style.color = ok ? "var(--success)" : "var(--error)";
    return ok;
  }

  function validateKey() {
    const v = $("f_api_key").value;
    const ok = v.length === 0 || v.length >= 10;
    $("hint_key").textContent = ok ? (v.length ? "✓" : "Optional") : "Min 10 characters";
    $("hint_key").style.color = ok ? "var(--success)" : "var(--error)";
    return ok;
  }

  $("f_api_url").addEventListener("input", validateApiUrl);
  $("f_api_key").addEventListener("input", validateKey);

  $("btnSaveProfile").addEventListener("click", async () => {
    let state = await globalThis.GspsStore.loadState();
    state.profile.name = $("f_name").value.trim() || "SERP Professional";
    state.profile.email = $("f_email").value.trim();
    const em = state.profile.email;
    if (em && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(em)) {
      toast("Invalid email format.", "error");
      return;
    }
    state.settings.defaultKeywordHint = $("f_keyword_hint").value.trim();
    const dl = parseInt($("f_daily_limit").value, 10) || 50;
    state.profile.preferences.dailyLimit = dl;
    state.usage.limit = dl;
    const sw = document.querySelector(".avatar-color-swatch.active");
    if (sw) state.profile.avatarColor = parseInt(sw.dataset.picked, 10) || 0;
    if (pendingAvatar === "__clear__") {
      state.profile.avatar = null;
      pendingAvatar = null;
    } else if (pendingAvatar) {
      state.profile.avatar = pendingAvatar;
      pendingAvatar = null;
    }
    await globalThis.GspsStore.saveState(state);
    toast("Profile saved.", "success");
    await loadAll();
  });

  $("btnPickAvatar").addEventListener("click", () => $("f_avatar_file").click());
  $("f_avatar_file").addEventListener("change", async () => {
    const f = $("f_avatar_file").files && $("f_avatar_file").files[0];
    if (!f) return;
    try {
      pendingAvatar = await globalThis.GspsProfile.processAvatarFile(f);
      const state = await globalThis.GspsStore.loadState();
      renderProfileAvatar(state);
    } catch (e) {
      toast(e.message || "Invalid image", "error");
    }
  });
  $("btnClearAvatar").addEventListener("click", async () => {
    pendingAvatar = "__clear__";
    $("f_avatar_file").value = "";
    const state = await globalThis.GspsStore.loadState();
    renderProfileAvatar(state);
    toast("Save profile to apply.", "info");
  });

  $("btnSaveSerp").addEventListener("click", async () => {
    let state = await globalThis.GspsStore.loadState();
    state.settings.defaultCountry = ($("f_country").value || "US").toUpperCase();
    state.settings.language = $("f_language").value;
    state.settings.device = $("f_device").value;
    state.settings.cacheTtl = parseInt($("f_cache_ttl").value, 10) || 3600;
    state.profile.preferences.defaultCountry = state.settings.defaultCountry;
    state.profile.preferences.defaultLanguage = state.settings.language;
    state.profile.preferences.defaultDevice = state.settings.device;
    await globalThis.GspsStore.saveState(state);
    toast("SERP settings saved.", "success");
    await loadAll();
  });

  $("f_cache_ttl").addEventListener("input", () => {
    $("ttlLabel").textContent = $("f_cache_ttl").value;
  });
  $("f_font_size").addEventListener("input", () => {
    const i = parseInt($("f_font_size").value, 10);
    $("fontLabel").textContent = FONT_KEYS[i] || "medium";
  });

  $("btnSaveApi").addEventListener("click", async () => {
    if (!validateApiUrl() || !validateKey()) {
      toast("Fix validation errors.", "error");
      return;
    }
    let state = await globalThis.GspsStore.loadState();
    state.settings.apiUrl = $("f_api_url").value.trim();
    state.settings.apiKey = $("f_api_key").value;
    await globalThis.GspsStore.saveState(state);
    toast("API credentials saved.", "success");
  });

  $("btnToggleKey").addEventListener("click", () => {
    const inp = $("f_api_key");
    const show = inp.type === "password";
    inp.type = show ? "text" : "password";
    $("btnToggleKey").textContent = show ? "Hide" : "Show";
  });

  $("btnTestApi").addEventListener("click", () => {
    if (!validateApiUrl()) return;
    const url = $("f_api_url").value.trim();
    chrome.runtime.sendMessage({ type: "TEST_API", url }, (r) => {
      if (chrome.runtime.lastError) {
        toast("Test failed: " + chrome.runtime.lastError.message, "error");
        return;
      }
      if (r && r.ok) toast(`Connection OK (HTTP ${r.status != null ? r.status : "—"}).`, "success");
      else toast("Failed: " + (r && r.error ? r.error : "unknown"), "error");
    });
  });

  $("btnSaveAppearance").addEventListener("click", async () => {
    let state = await globalThis.GspsStore.loadState();
    const th = document.querySelector('input[name="theme"]:checked');
    state.settings.theme = th ? th.value : "system";
    const chip = document.querySelector(".accent-chip.active");
    if (chip) state.settings.accent = chip.getAttribute("data-accent");
    const fi = parseInt($("f_font_size").value, 10);
    state.settings.fontSize = FONT_KEYS[fi] || "medium";
    await globalThis.GspsStore.saveState(state);
    applyShell(state);
    toast("Appearance saved.", "success");
  });

  document.querySelectorAll(".accent-chip").forEach((chip) => {
    chip.addEventListener("click", () => {
      document.querySelectorAll(".accent-chip").forEach((c) => c.classList.remove("active"));
      chip.classList.add("active");
      document.documentElement.setAttribute("data-accent", chip.getAttribute("data-accent"));
    });
  });

  $("btnQuickSerp").addEventListener("click", async () => {
    try {
      let state = await globalThis.GspsStore.loadState();
      const kw = state.settings.defaultKeywordHint || "best SEO tools";
      const res = await globalThis.GspsSerp.analyzeKeyword(kw);
      const before = new Set(state.profile.achievements || []);
      globalThis.GspsStore.appendAnalysisResult(state, res);
      globalThis.GspsAchievements.evaluate(state);
      const newA = state.profile.achievements.filter((a) => !before.has(a));
      await globalThis.GspsStore.saveState(state);
      newA.forEach((a) => toast(`Unlocked: ${globalThis.GspsAchievements.label(a)}`, "success"));
      toast("Test SERP completed.", "success");
      await loadAll();
    } catch (e) {
      toast(e.message || "Test failed", "error");
    }
  });

  $("btnClearCache").addEventListener("click", async () => {
    if (!confirm("Clear all history entries?")) return;
    await globalThis.GspsStore.clearHistory();
    toast("History cleared.", "success");
    await loadAll();
  });

  $("btnProcessQueue").addEventListener("click", () => {
    chrome.runtime.sendMessage({ type: "PROCESS_QUEUE" }, () => toast("Queue processed.", "info"));
  });

  $("histFilter").addEventListener("input", () => {
    clearTimeout(filterDebounce);
    filterDebounce = setTimeout(async () => {
      histPage = 0;
      const state = await globalThis.GspsStore.loadState();
      renderHistoryTable(state);
    }, 300);
  });
  $("histSort").addEventListener("change", async () => {
    const state = await globalThis.GspsStore.loadState();
    renderHistoryTable(state);
  });
  $("btnHistPrev").addEventListener("click", async () => {
    if (histPage > 0) histPage--;
    const state = await globalThis.GspsStore.loadState();
    renderHistoryTable(state);
  });
  $("btnHistNext").addEventListener("click", async () => {
    const state = await globalThis.GspsStore.loadState();
    const n = getFilteredHistory(state).length;
    if ((histPage + 1) * HIST_PAGE < n) histPage++;
    renderHistoryTable(state);
  });

  $("btnExportHistCsv").addEventListener("click", async () => {
    const state = await globalThis.GspsStore.loadState();
    const csv = globalThis.GspsHistory.exportData(getFilteredHistory(state), "csv");
    globalThis.GspsBackup.download("gsps-history.csv", csv);
  });
  $("btnExportHistJson").addEventListener("click", async () => {
    const state = await globalThis.GspsStore.loadState();
    const j = globalThis.GspsHistory.exportData(getFilteredHistory(state), "json");
    globalThis.GspsBackup.download("gsps-history.json", j);
  });

  $("btnClearAllHist").addEventListener("click", async () => {
    const v = prompt('Type CONFIRM to delete all history:');
    if (v !== "CONFIRM") return;
    let state = await globalThis.GspsStore.loadState();
    state.history = [];
    await globalThis.GspsStore.saveState(state);
    toast("All history deleted.", "success");
    await loadAll();
  });

  $("btnExportFull").addEventListener("click", async () => {
    const state = await globalThis.GspsStore.loadState();
    const json = JSON.stringify(globalThis.GspsBackup.buildExport(state), null, 2);
    globalThis.GspsBackup.download(`gspsp-backup-${globalThis.GspsState.todayKey()}.json`, json);
  });

  $("btnImport").addEventListener("click", async () => {
    const f = $("importFile").files && $("importFile").files[0];
    if (!f) {
      toast("Choose a file.", "warning");
      return;
    }
    const mode = document.querySelector('input[name="importMode"]:checked').value;
    const text = await f.text();
    try {
      const cur = await globalThis.GspsStore.loadState();
      const merged = globalThis.GspsBackup.parseImport(text, mode === "replace" ? "replace" : "merge", cur);
      await globalThis.GspsStore.saveState(merged);
      toast("Import complete.", "success");
      await loadAll();
    } catch (e) {
      toast(e.message || "Import failed", "error");
    }
  });

  $("batchFile").addEventListener("change", async () => {
    const f = $("batchFile").files && $("batchFile").files[0];
    if (!f) return;
    csvText = await f.text();
    $("batchPreview").textContent = csvText.slice(0, 4000);
  });

  $("btnRunBatch").addEventListener("click", async () => {
    if (!csvText) {
      toast("Select a CSV file first.", "warning");
      return;
    }
    const rows = globalThis.GspsBatch.parseCsv(csvText);
    if (!rows.length) {
      toast("No valid rows.", "error");
      return;
    }
    $("batchProgress").textContent = "Running…";
    let state = await globalThis.GspsStore.loadState();
    state.meta.maxBatchOnce = Math.max(state.meta.maxBatchOnce || 0, rows.length);
    state.meta.totalBatchEver = (state.meta.totalBatchEver || 0) + rows.length;
    for (let i = 0; i < rows.length; i++) {
      const row = rows[i];
      $("batchProgress").textContent = `Processing ${i + 1}/${rows.length}…`;
      try {
        const res = await globalThis.GspsSerp.analyzeKeyword(row.keyword);
        const before = new Set(state.profile.achievements || []);
        globalThis.GspsStore.appendAnalysisResult(state, res);
        globalThis.GspsAchievements.evaluate(state);
        await globalThis.GspsStore.saveState(state);
      } catch (e) {
        toast(`Row ${i + 1}: ${e.message}`, "warning");
      }
    }
    globalThis.GspsAchievements.evaluate(state);
    await globalThis.GspsStore.saveState(state);
    $("batchProgress").textContent = `Done (${rows.length} keywords).`;
    toast("Batch complete.", "success");
    await loadAll();
  });

  $("btnPngExport").addEventListener("click", () => {
    const c = $("chartLine");
    if (c) globalThis.GspsCharts.exportPng(c);
  });

  window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", async () => {
    const state = await globalThis.GspsStore.loadState();
    if (state.settings.theme === "system") applyShell(state);
  });

  async function boot() {
    const { optionsTab, pendingExport } = await chrome.storage.local.get(["optionsTab", "pendingExport"]);
    if (optionsTab) {
      showPage(optionsTab);
      await chrome.storage.local.remove("optionsTab");
    }
    if (pendingExport) {
      globalThis.GspsBackup.download(`gspsp-backup-${globalThis.GspsState.todayKey()}.json`, pendingExport);
      await chrome.storage.local.remove("pendingExport");
    }
    await loadAll();
    if (globalThis.GspsShortcuts) globalThis.GspsShortcuts.init();
  }

  boot();
})();
