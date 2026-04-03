/**
 * GSPS SERP Pro — popup controller (v3).
 */
(function () {
  const $ = (id) => document.getElementById(id);
  const MSG = (k) => (chrome.i18n && chrome.i18n.getMessage(k)) || "";
  let offlineWarned = false;

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
    const n = (name || "SERP Professional").trim() || "there";
    return `${part}, ${n}`;
  }

  function relTime(ts) {
    const d = new Date(ts);
    const day = new Date();
    const y = new Date(day);
    y.setDate(y.getDate() - 1);
    if (d.toDateString() === y.toDateString()) return "yesterday";
    const s = Math.floor((Date.now() - d.getTime()) / 1000);
    if (s < 60) return "just now";
    const m = Math.floor(s / 60);
    if (m < 60) return `${m} min ago`;
    const h = Math.floor(m / 60);
    if (h < 24) return `${h} hr ago`;
    return `${Math.floor(h / 24)} d ago`;
  }

  function resolvedDark(settings) {
    if (settings.theme === "dark") return true;
    if (settings.theme === "light") return false;
    return window.matchMedia("(prefers-color-scheme: dark)").matches;
  }

  function applyTheme(settings) {
    const dark = resolvedDark(settings);
    document.body.classList.toggle("dark-mode", dark);
    const btn = $("btnThemeToggle");
    if (btn) btn.textContent = dark ? "☀️" : "🌙";
  }

  function notify(msg, type) {
    const host = $("toastHost");
    if (globalThis.GspsNotify && host) {
      globalThis.GspsNotify.show(host, msg, type || "info");
    }
  }

  function confettiBurst() {
    const host = document.createElement("div");
    host.className = "gsps-confetti-host";
    const colors = ["#3B82F6", "#8B5CF6", "#EC4899", "#10B981"];
    for (let i = 0; i < 28; i++) {
      const d = document.createElement("div");
      d.className = "gsps-confetti-dot";
      d.style.left = Math.random() * 100 + "%";
      d.style.top = "18%";
      d.style.background = colors[i % colors.length];
      d.style.animationDelay = i * 0.04 + "s";
      host.appendChild(d);
    }
    document.body.appendChild(host);
    setTimeout(() => host.remove(), 1600);
  }

  function ringAnimate(used, limit) {
    const r = 18;
    const c = 2 * Math.PI * r;
    const fg = $("usageRingFg");
    const target = limit > 0 ? Math.min(1, used / limit) : 0;
    const pct = globalThis.GspsUsage.percent(used, limit);
    const col = globalThis.GspsUsage.ringColor(pct);
    document.documentElement.style.setProperty("--ring-use", col);
    const wrap = $("btnUsageRing");
    if (wrap) wrap.classList.toggle("ring-pulse", pct >= 90);
    let start = null;
    const dur = 1000;
    function frame(t) {
      if (!start) start = t;
      const p = Math.min(1, (t - start) / dur);
      const eased = 1 - Math.pow(1 - p, 3);
      const off = c * (1 - target * eased);
      fg.style.strokeDasharray = String(c);
      fg.style.strokeDashoffset = String(off);
      if (p < 1) requestAnimationFrame(frame);
    }
    requestAnimationFrame(frame);
    $("usageRingLabel").textContent = `${used}/${limit}`;
  }

  function renderAvatar(state) {
    const inner = $("avatarInner");
    const ring = $("avatarRing");
    const ini = initials(state.profile.name);
    const grad = globalThis.GspsProfile.gradientForIndex(state.profile.avatarColor || 0);
    if (ring) ring.style.background = grad;
    if (state.profile.avatar) {
      inner.innerHTML = `<img src="" alt="User avatar" />`;
      const img = inner.querySelector("img");
      img.src = state.profile.avatar;
    } else {
      inner.innerHTML = `<span id="avatarInitials">${ini}</span>`;
    }
    $("welcomeLine").textContent = greetingForHour(state.profile.name);
    $("streakLine").textContent = `🔥 ${state.profile.streak.current || 0} day streak`;
  }

  function renderSuggestions(state) {
    const row = $("suggestRow");
    const chips = $("suggestChips");
    const counts = state.analytics.keywordCounts || {};
    const top = Object.entries(counts)
      .sort((a, b) => b[1] - a[1])
      .slice(0, 5)
      .map((x) => x[0]);
    if (!top.length) {
      row.style.display = "none";
      return;
    }
    row.style.display = "block";
    chips.innerHTML = "";
    for (const kw of top) {
      const b = document.createElement("button");
      b.type = "button";
      b.textContent = kw;
      b.setAttribute("aria-label", "Analyze " + kw);
      b.addEventListener("click", () => runKeyword(kw));
      chips.appendChild(b);
    }
  }

  function renderHistory(state) {
    const ul = $("recentList");
    const empty = $("recentEmpty");
    ul.innerHTML = "";
    const top = (state.history || []).slice(0, 3);
    if (!top.length) {
      empty.style.display = "block";
      return;
    }
    empty.style.display = "none";
    for (const row of top) {
      const li = document.createElement("li");
      const kw = escapeHtml(row.keyword || "");
      const ts = row.timestamp ? new Date(row.timestamp).getTime() : Date.now();
      li.innerHTML =
        `<button type="button" class="recent-item-btn" title="${escapeHtml(new Date(ts).toLocaleString())}">` +
        `<span class="dot ${row.success !== false ? "ok" : "bad"}"></span>` +
        `<span class="kw">${kw}</span>` +
        `<span class="sub">${escapeHtml(String(row.resultsCount || 0))} results · ${relTime(ts)}</span>` +
        `</button>`;
      li.querySelector("button").addEventListener("click", () => runKeyword(row.keyword));
      ul.appendChild(li);
    }
  }

  function escapeHtml(s) {
    const d = document.createElement("div");
    d.textContent = s;
    return d.innerHTML;
  }

  async function refresh() {
    let state = await globalThis.GspsStore.loadState();
    globalThis.GspsState.normalizeDay(state);
    document.documentElement.setAttribute("data-accent", state.settings.accent || "purple");
    document.documentElement.classList.remove("fs-small", "fs-medium", "fs-large");
    document.documentElement.classList.add("fs-" + (state.settings.fontSize || "medium"));
    applyTheme(state.settings);
    renderAvatar(state);
    const lim = state.usage.limit || state.profile.preferences.dailyLimit || 50;
    ringAnimate(state.usage.today || 0, lim);
    renderSuggestions(state);
    renderHistory(state);
    const ver = chrome.runtime.getManifest().version;
    $("footerBrand").textContent = `GSPS SERP Pro · v${ver}`;
    const limited = !globalThis.GspsUsage.canUse(state);
    $("btnAnalyzeSerp").disabled = limited;
    $("btnGenerateContent").disabled = limited;
    if (!navigator.onLine && !offlineWarned) {
      offlineWarned = true;
      notify("You appear offline. Actions will queue when possible.", "warning");
    }
    try {
      await chrome.runtime.sendMessage({ type: "REFRESH_BADGE" });
    } catch (_) {}
  }

  async function delayMin(ms, start) {
    const el = Date.now() - start;
    if (el < ms) await new Promise((r) => setTimeout(r, ms - el));
  }

  async function runKeyword(keyword) {
    const t0 = Date.now();
    $("recentSkeleton").style.display = "block";
    try {
      let state = await globalThis.GspsStore.loadState();
      if (!globalThis.GspsUsage.canUse(state)) {
        notify(MSG("errorLimit") || "Daily limit reached.", "error");
        return;
      }
      const before = new Set(state.profile.achievements || []);
      const res = await globalThis.GspsSerp.analyzeKeyword(keyword);
      globalThis.GspsStore.appendAnalysisResult(state, res);
      milestoneCelebration(state, before);
      await globalThis.GspsStore.saveState(state);
      await delayMin(300, t0);
      notify(`Analyzed: ${(res.keyword || "").slice(0, 48)}`, "success");
      await refresh();
    } catch (e) {
      if (e && e.code === "LIMIT") notify(MSG("errorLimit") || "Daily limit reached.", "warning");
      else notify(e.message || "Analysis failed", "error");
    } finally {
      $("recentSkeleton").style.display = "none";
    }
  }

  function milestoneCelebration(state, before) {
    const now = state.profile.achievements || [];
    const newAch = now.filter((a) => !before.has(a));
    for (const a of newAch) {
      notify(`Unlocked: ${globalThis.GspsAchievements.label(a)}`, "success");
      if (a === "streak_7" || a === "streak_30" || a === "power_user") confettiBurst();
    }
  }

  async function runSerp(e) {
    if (e) ripple($("btnAnalyzeSerp"), e);
    const t0 = Date.now();
    $("recentSkeleton").style.display = "block";
    try {
      let state = await globalThis.GspsStore.loadState();
      if (!globalThis.GspsUsage.canUse(state)) {
        notify(MSG("errorLimit") || "Daily limit reached.", "error");
        return;
      }
      const before = new Set(state.profile.achievements || []);
      const res = await globalThis.GspsSerp.analyzeActiveTab();
      globalThis.GspsStore.appendAnalysisResult(state, res);
      milestoneCelebration(state, before);
      await globalThis.GspsStore.saveState(state);
      await delayMin(300, t0);
      notify(`SERP: ${(res.keyword || "").slice(0, 48)}`, "success");
      await refresh();
    } catch (err) {
      if (err && err.code === "LIMIT") notify(MSG("errorLimit") || "Daily limit reached.", "warning");
      else notify(err.message || "SERP analysis failed.", "error");
    } finally {
      $("recentSkeleton").style.display = "none";
    }
  }

  async function runContent(e) {
    if (e) ripple($("btnGenerateContent"), e);
    const t0 = Date.now();
    $("recentSkeleton").style.display = "block";
    try {
      let state = await globalThis.GspsStore.loadState();
      if (!globalThis.GspsUsage.canUse(state)) {
        notify(MSG("errorLimit") || "Daily limit reached.", "error");
        return;
      }
      const before = new Set(state.profile.achievements || []);
      const res = await globalThis.GspsSerp.generateContent();
      globalThis.GspsStore.appendContentResult(state, res.text || res.keyword || "Generated");
      milestoneCelebration(state, before);
      await globalThis.GspsStore.saveState(state);
      await delayMin(300, t0);
      notify("Content generated.", "success");
      await refresh();
    } catch (err) {
      notify(err.message || "Content generation failed.", "error");
    } finally {
      $("recentSkeleton").style.display = "none";
    }
  }

  function ripple(btn, e) {
    const sp = document.createElement("span");
    sp.className = "ripple";
    const rect = btn.getBoundingClientRect();
    const x = (e.clientX || rect.left + rect.width / 2) - rect.left;
    const y = (e.clientY || rect.top + rect.height / 2) - rect.top;
    const d = Math.max(rect.width, rect.height) * 2;
    sp.style.width = sp.style.height = d + "px";
    sp.style.left = x - d / 2 + "px";
    sp.style.top = y - d / 2 + "px";
    btn.appendChild(sp);
    setTimeout(() => sp.remove(), 600);
  }

  $("btnEditProfile").addEventListener("click", () => {
    chrome.storage.local.set({ optionsTab: "profile" });
    chrome.runtime.openOptionsPage();
  });
  $("btnUsageRing").addEventListener("click", () => {
    chrome.storage.local.set({ optionsTab: "analytics" });
    chrome.runtime.openOptionsPage();
  });
  $("btnAnalyzeSerp").addEventListener("click", (e) => {
    ripple($("btnAnalyzeSerp"), e);
    runSerp(e);
  });
  $("btnGenerateContent").addEventListener("click", (e) => runContent(e));

  $("btnClearHistory").addEventListener("click", async () => {
    if (!confirm("Clear all recent activity from this device?")) return;
    await globalThis.GspsStore.clearHistory();
    notify("History cleared.", "success");
    await refresh();
  });

  $("btnThemeToggle").addEventListener("click", async () => {
    const state = await globalThis.GspsStore.loadState();
    const cur = resolvedDark(state.settings);
    state.settings.theme = cur ? "light" : "dark";
    await globalThis.GspsStore.saveState(state);
    applyTheme(state.settings);
    notify(`Theme: ${state.settings.theme}`, "info");
  });

  window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", async () => {
    const state = await globalThis.GspsStore.loadState();
    if (state.settings.theme === "system") applyTheme(state.settings);
  });

  async function consumePending() {
    const { pendingAnalyze } = await chrome.storage.local.get("pendingAnalyze");
    if (pendingAnalyze && pendingAnalyze.keyword) {
      await chrome.storage.local.remove("pendingAnalyze");
      await runKeyword(pendingAnalyze.keyword);
    }
  }

  if (globalThis.GspsShortcuts) globalThis.GspsShortcuts.init();

  refresh().then(() => consumePending());
})();
