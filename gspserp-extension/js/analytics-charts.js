/**
 * Canvas charts (line, bar, pie, heatmap) + PNG export — no external libs.
 */
(function () {
  function setupHiDPI(canvas, cssW, cssH) {
    const dpr = window.devicePixelRatio || 1;
    canvas.width = cssW * dpr;
    canvas.height = cssH * dpr;
    canvas.style.width = cssW + "px";
    canvas.style.height = cssH + "px";
    const ctx = canvas.getContext("2d");
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    return ctx;
  }

  /**
   * @param {HTMLCanvasElement} canvas
   * @param {Record<string, number>} dailyUsage last 30 days keys YYYY-MM-DD
   */
  function drawLineUsage(canvas, dailyUsage) {
    const w = canvas.clientWidth || 400;
    const h = 180;
    const ctx = setupHiDPI(canvas, w, h);
    ctx.clearRect(0, 0, w, h);
    const days = [];
    for (let i = 29; i >= 0; i--) {
      const d = new Date();
      d.setDate(d.getDate() - i);
      const key = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
      days.push({ key, v: dailyUsage[key] || 0 });
    }
    const max = Math.max(1, ...days.map((x) => x.v));
    const pad = 24;
    ctx.strokeStyle = "rgba(148,163,184,0.5)";
    ctx.beginPath();
    ctx.moveTo(pad, h - pad);
    ctx.lineTo(w - pad, h - pad);
    ctx.stroke();
    ctx.strokeStyle = "#3B82F6";
    ctx.lineWidth = 2;
    ctx.beginPath();
    days.forEach((d, i) => {
      const x = pad + (i / (days.length - 1 || 1)) * (w - 2 * pad);
      const y = h - pad - (d.v / max) * (h - 2 * pad);
      if (i === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    });
    ctx.stroke();
  }

  /**
   * @param {HTMLCanvasElement} canvas
   * @param {Record<string, number>} keywordCounts
   */
  function drawBarKeywords(canvas, keywordCounts) {
    const entries = Object.entries(keywordCounts || {})
      .sort((a, b) => b[1] - a[1])
      .slice(0, 10);
    const w = canvas.clientWidth || 400;
    const h = 220;
    const ctx = setupHiDPI(canvas, w, h);
    ctx.clearRect(0, 0, w, h);
    const max = Math.max(1, ...entries.map((x) => x[1]));
    const rowH = Math.min(28, (h - 20) / (entries.length || 1));
    entries.forEach((e, i) => {
      const y = 10 + i * rowH;
      const bw = ((e[1] / max) * (w - 120)) | 0;
      ctx.fillStyle = "rgba(59,130,246,0.25)";
      ctx.fillRect(100, y, w - 120, rowH - 4);
      ctx.fillStyle = "#8B5CF6";
      ctx.fillRect(100, y, bw, rowH - 4);
      ctx.fillStyle = "#64748B";
      ctx.font = "11px Inter, system-ui, sans-serif";
      ctx.fillText(e[0].slice(0, 18), 4, y + rowH / 2 + 3);
      ctx.fillText(String(e[1]), w - 36, y + rowH / 2 + 3);
    });
  }

  /**
   * @param {HTMLCanvasElement} canvas
   * @param {number} ok
   * @param {number} fail
   */
  function drawPieSuccess(canvas, ok, fail) {
    const w = 200;
    const h = 200;
    const ctx = setupHiDPI(canvas, w, h);
    ctx.clearRect(0, 0, w, h);
    const t = ok + fail || 1;
    const aOk = (ok / t) * Math.PI * 2;
    ctx.beginPath();
    ctx.moveTo(100, 100);
    ctx.arc(100, 100, 80, -Math.PI / 2, -Math.PI / 2 + aOk);
    ctx.closePath();
    ctx.fillStyle = "#10B981";
    ctx.fill();
    ctx.beginPath();
    ctx.moveTo(100, 100);
    ctx.arc(100, 100, 80, -Math.PI / 2 + aOk, -Math.PI / 2 + Math.PI * 2);
    ctx.closePath();
    ctx.fillStyle = "#EF4444";
    ctx.fill();
    const pct = Math.round((ok / t) * 100);
    ctx.fillStyle = "#1E293B";
    ctx.font = "600 18px Inter, system-ui, sans-serif";
    ctx.textAlign = "center";
    ctx.fillText(pct + "%", 100, 104);
  }

  /**
   * @param {HTMLCanvasElement} canvas
   * @param {number[]} hourly 24 ints
   */
  function drawHeatmap(canvas, hourly) {
    const w = canvas.clientWidth || 400;
    const h = 120;
    const ctx = setupHiDPI(canvas, w, h);
    ctx.clearRect(0, 0, w, h);
    const max = Math.max(1, ...hourly);
    const cell = (w - 40) / 24;
    for (let i = 0; i < 24; i++) {
      const intensity = hourly[i] / max;
      ctx.fillStyle = `rgba(59,130,246,${0.15 + intensity * 0.85})`;
      ctx.fillRect(20 + i * cell, 20, cell - 2, 60);
      ctx.fillStyle = "#64748B";
      ctx.font = "9px system-ui";
      ctx.fillText(String(i), 20 + i * cell, 100);
    }
  }

  /**
   * @param {HTMLCanvasElement} canvas
   */
  function exportPng(canvas) {
    const a = document.createElement("a");
    a.href = canvas.toDataURL("image/png");
    a.download = "gsps-chart.png";
    a.click();
  }

  globalThis.GspsCharts = {
    drawLineUsage,
    drawBarKeywords,
    drawPieSuccess,
    drawHeatmap,
    exportPng,
  };
})();
