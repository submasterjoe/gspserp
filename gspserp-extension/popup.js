/**
 * GSPS Pro popup — profile-first, storage via GspsStore, SERP via GspsSerp.
 */
(function () {
  const $ = (id) => document.getElementById(id);

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
    const n = (name || "SERP Pro").trim() || "there";
    return `${part}, ${n}`;
  }

  function relTime(ts) {
    const s = Math.floor((Date.now() - ts) / 1000);
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

  function showToast(msg, ok) {
    const host = $("toastHost");
    const el = document.createElement("div");
    el.className = "toast" + (ok ? " ok" : "");
    el.textContent = msg;
    host.appendChild(el);
    setTimeout(() => {
      el.style.opacity = "0";
      el.style.transform = "translateX(8px)";
      el.style.transition = "0.25s ease";
      setTimeout(() => el.remove(), 260);
    }, 3000);
  }

  function ringUpdate(used, limit) {
    const r = 18;
    const c = 2 * Math.PI * r;
    const pct = limit > 0 ? Math.min(1, used / limit) : 0;
    const fg = $("usageRingFg");
    if (fg) {
      fg.style.strokeDasharray = `${c}`;
      fg.style.strokeDashoffset = `${c * (1 - pct)}`;
    }
    const lbl = $("usageRingLabel");
    if (lbl) lbl.textContent = `${used}/${limit}`;
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

  function renderAvatar(state) {
    const inner = $("avatarInner");
    const ini = initials(state.profile.name);
    if (state.profile.avatar) {
      inner.innerHTML = `<img src="" alt="" />`;
      const img = inner.querySelector("img");
      img.src = state.profile.avatar;
    } else {
      inner.innerHTML = `<span id="avatarInitials">${ini}</span>`;
    }
    $("welcomeLine").textContent = greetingForHour(state.profile.name);
    $("streakLine").textContent = `🔥 ${state.profile.streak || 0} day streak`;
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
      const q = escapeHtml(row.query || "");
      li.innerHTML = `<div>${q}</div><div class="sub">${escapeHtml(row.engine || "")} · ${relTime(row.ts)}</div>`;
      ul.appendChild(li);
    }
  }

  function escapeHtml(s) {
    const d = document.createElement("div");
    d.textContent = s;
    return d.innerHTML;
  }

  async function refresh() {
    const state = await GspsStore.loadState();
    document.documentElement.setAttribute("data-accent", state.settings.accent || "purple");
    document.documentElement.classList.remove("fs-small", "fs-medium", "fs-large");
    document.documentElement.classList.add("fs-" + (state.settings.fontSize || "medium"));
    applyTheme(state.settings);
    renderAvatar(state);
    ringUpdate(state.usage.today || 0, state.usage.limit || 50);
    renderHistory(state);
    const ver = chrome.runtime.getManifest().version;
    $("footerBrand").textContent = `GSPS Pro · v${ver}`;
  }

  async function runSerp() {
    $("recentSkeleton").style.display = "block";
    try {
      const res = await GspsSerp.analyzeActiveTab();
      let state = await GspsStore.loadState();
      state = GspsStore.appendAnalysisResult(state, res);
      await GspsStore.saveState(state);
      showToast(`SERP: ${(res.keyword || "").slice(0, 48)}${(res.keyword || "").length > 48 ? "…" : ""}`, true);
      await refresh();
    } catch (e) {
      console.error(e);
      showToast("SERP analysis failed.", false);
    } finally {
      $("recentSkeleton").style.display = "none";
    }
  }

  async function runContent(e) {
    if (e) ripple($("btnGenerateContent"), e);
    $("recentSkeleton").style.display = "block";
    try {
      const res = await GspsSerp.generateContent();
      let state = await GspsStore.loadState();
      state = GspsStore.appendContentResult(state, res.text || res.keyword || "Generated");
      await GspsStore.saveState(state);
      showToast("Content generated.", true);
      await refresh();
    } catch (err) {
      console.error(err);
      showToast("Content generation failed.", false);
    } finally {
      $("recentSkeleton").style.display = "none";
    }
  }

  $("btnEditProfile").addEventListener("click", () => chrome.runtime.openOptionsPage());
  $("btnAnalyzeSerp").addEventListener("click", (e) => {
    ripple($("btnAnalyzeSerp"), e);
    runSerp();
  });
  $("btnGenerateContent").addEventListener("click", (e) => runContent(e));

  $("btnClearHistory").addEventListener("click", async () => {
    await GspsStore.clearHistory();
    showToast("History cleared.", true);
    await refresh();
  });

  $("btnThemeToggle").addEventListener("click", async () => {
    const state = await GspsStore.loadState();
    const cur = resolvedDark(state.settings);
    state.settings.theme = cur ? "light" : "dark";
    await GspsStore.saveState(state);
    applyTheme(state.settings);
    showToast(`Theme: ${state.settings.theme}`, true);
  });

  window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", async () => {
    const state = await GspsStore.loadState();
    if (state.settings.theme === "system") applyTheme(state.settings);
  });

  refresh();
})();
