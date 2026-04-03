/**
 * Achievement unlocks and milestone checks.
 */
(function () {
  const DEFS = {
    first_search: { label: "First SERP Analysis" },
    power_user: { label: "Power User" },
    night_owl: { label: "Night Owl" },
    weekend_warrior: { label: "Weekend Warrior" },
    streak_7: { label: "Weekly Warrior" },
    streak_30: { label: "Monthly Master" },
    batch_king: { label: "Batch King" },
    api_master: { label: "API Master" },
  };

  /**
   * @param {object} state
   * @returns {string[]} newly unlocked ids
   */
  function evaluate(state) {
    const have = new Set(state.profile.achievements || []);
    const unlocked = [];

    const total = state.usage.totalAllTime || 0;
    if (total >= 1 && !have.has("first_search")) {
      unlocked.push("first_search");
    }
    if (total >= 100 && !have.has("power_user")) {
      unlocked.push("power_user");
    }
    if ((state.meta.nightOwlSearches || 0) >= 10 && !have.has("night_owl")) {
      unlocked.push("night_owl");
    }
    if ((state.meta.weekendSearches || 0) >= 20 && !have.has("weekend_warrior")) {
      unlocked.push("weekend_warrior");
    }
    if ((state.profile.streak.current || 0) >= 7 && !have.has("streak_7")) {
      unlocked.push("streak_7");
    }
    if ((state.profile.streak.current || 0) >= 30 && !have.has("streak_30")) {
      unlocked.push("streak_30");
    }
    if ((state.meta.maxBatchOnce || 0) >= 50 && !have.has("batch_king")) {
      unlocked.push("batch_king");
    }
    if ((state.usage.successfulApiCalls || 0) >= 1000 && !have.has("api_master")) {
      unlocked.push("api_master");
    }

    for (const u of unlocked) {
      have.add(u);
    }
    state.profile.achievements = Array.from(have);
    return unlocked;
  }

  /**
   * @param {string} id
   */
  function label(id) {
    return DEFS[id] ? DEFS[id].label : id;
  }

  globalThis.GspsAchievements = {
    evaluate,
    label,
    DEFS,
  };
})();
