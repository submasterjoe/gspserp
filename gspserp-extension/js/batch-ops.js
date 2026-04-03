/**
 * CSV batch SERP analysis: parse, queue, concurrent workers (max 5).
 */
(function () {
  /**
   * @param {string} csvText
   * @returns {Array<{keyword:string,country?:string,device?:string}>}
   */
  function parseCsv(csvText) {
    const lines = csvText.split(/\r?\n/).filter((l) => l.trim());
    const out = [];
    for (let i = 0; i < lines.length && out.length < 100; i++) {
      const parts = lines[i].split(",").map((p) => p.trim().replace(/^"|"$/g, ""));
      if (!parts[0]) continue;
      out.push({
        keyword: parts[0],
        country: parts[1] || "US",
        device: (parts[2] || "desktop").toLowerCase() === "mobile" ? "mobile" : "desktop",
      });
    }
    return out;
  }

  /**
   * @param {Array<object>} rows
   * @param {(row: object, i: number) => Promise<object>} worker
   * @param {{ concurrency?: number, onProgress?: (n:number,total:number)=>void }} opts
   */
  async function runBatch(rows, worker, opts) {
    opts = opts || {};
    const conc = Math.min(5, opts.concurrency || 5);
    let i = 0;
    const results = [];
    const total = rows.length;

    async function runOne() {
      while (i < total) {
        const idx = i++;
        const row = rows[idx];
        try {
          const r = await worker(row, idx);
          results[idx] = { ok: true, row, result: r };
        } catch (e) {
          results[idx] = { ok: false, row, error: e.message || String(e) };
        }
        if (opts.onProgress) opts.onProgress(results.filter(Boolean).length, total);
      }
    }

    const pool = [];
    for (let c = 0; c < conc; c++) pool.push(runOne());
    await Promise.all(pool);
    return results;
  }

  function resultsToCsv(results) {
    const hdr = "keyword,success,resultsCount,error";
    const lines = [hdr];
    for (const r of results) {
      if (!r) continue;
      const kw = r.row.keyword;
      if (r.ok) {
        const rc = r.result?.resultsCount != null ? r.result.resultsCount : "";
        lines.push(`"${kw.replace(/"/g, '""')}",true,${rc},""`);
      } else {
        lines.push(`"${kw.replace(/"/g, '""')}",false,,"${(r.error || "").replace(/"/g, '""')}"`);
      }
    }
    return lines.join("\n");
  }

  globalThis.GspsBatch = {
    parseCsv,
    runBatch,
    resultsToCsv,
  };
})();
