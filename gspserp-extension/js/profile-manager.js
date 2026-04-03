/**
 * Profile: initials avatar gradients, image resize (max 500KB), streak updates.
 */
(function () {
  const GRADIENTS = [
    "linear-gradient(135deg,#3B82F6,#8B5CF6)",
    "linear-gradient(135deg,#EC4899,#F59E0B)",
    "linear-gradient(135deg,#10B981,#3B82F6)",
    "linear-gradient(135deg,#8B5CF6,#EC4899)",
    "linear-gradient(135deg,#F59E0B,#EF4444)",
    "linear-gradient(135deg,#06B6D4,#3B82F6)",
    "linear-gradient(135deg,#84CC16,#059669)",
  ];

  /**
   * @param {string} name
   */
  function initials(name) {
    const t = (name || "").trim();
    if (!t) return "JD";
    const p = t.split(/\s+/).slice(0, 2);
    return p.map((x) => x[0].toUpperCase()).join("") || "JD";
  }

  /**
   * @param {number} id
   */
  function gradientForIndex(id) {
    return GRADIENTS[Math.abs(id) % GRADIENTS.length];
  }

  /**
   * @param {File} file
   * @returns {Promise<string>} data URL
   */
  function processAvatarFile(file) {
    return new Promise((resolve, reject) => {
      if (!file || !file.type.startsWith("image/")) {
        reject(new Error("Invalid image"));
        return;
      }
      if (file.size > 500 * 1024) {
        reject(new Error("Image must be 500KB or smaller"));
        return;
      }
      const reader = new FileReader();
      reader.onload = () => {
        const img = new Image();
        img.onload = () => {
          try {
            const max = 128;
            let w = img.width;
            let h = img.height;
            const scale = Math.min(1, max / Math.max(w, h));
            w = Math.round(w * scale);
            h = Math.round(h * scale);
            const c = document.createElement("canvas");
            c.width = w;
            c.height = h;
            const ctx = c.getContext("2d");
            ctx.drawImage(img, 0, 0, w, h);
            resolve(c.toDataURL("image/png"));
          } catch (e) {
            reject(e);
          }
        };
        img.onerror = () => reject(new Error("Could not decode image"));
        img.src = reader.result;
      };
      reader.onerror = () => reject(new Error("Read failed"));
      reader.readAsDataURL(file);
    });
  }

  /**
   * Streak: &lt;24h same window; 24–48h increments; ≥48h resets to 1.
   * @param {object} state
   * @returns {object} state (mutated)
   */
  function updateStreakOnActivity(state) {
    const now = Date.now();
    const last = state.profile.streak.lastUsed ? new Date(state.profile.streak.lastUsed).getTime() : 0;
    const deltaH = last ? (now - last) / (3600 * 1000) : Infinity;
    if (!last) {
      state.profile.streak.current = 1;
    } else if (deltaH < 24) {
      /* keep count */
    } else if (deltaH < 48) {
      state.profile.streak.current = (state.profile.streak.current || 0) + 1;
    } else {
      state.profile.streak.current = 1;
    }
    state.profile.streak.lastUsed = new Date().toISOString();
    if (state.profile.streak.current > state.profile.streak.longest) {
      state.profile.streak.longest = state.profile.streak.current;
    }
    return state;
  }

  globalThis.GspsProfile = {
    initials,
    gradientForIndex,
    processAvatarFile,
    updateStreakOnActivity,
    GRADIENTS,
  };
})();
