(() => {
  const messagesEl = document.getElementById("messages");
  const inputEl = document.getElementById("chatInput");
  const sendBtn = document.getElementById("sendBtn");
  const statusDotEl = document.getElementById("statusDot");
  const statusTextEl = document.getElementById("statusText");
  const liveStateEl = document.getElementById("liveState");
  const PROFILE_INPUT_IDS = [
    "p-age",
    "p-weight",
    "p-height",
    "p-gender",
    "p-goal",
    "p-level",
    "p-equipment",
    "p-duration",
    "p-frequency",
    "p-limitations",
    "p-diet",
    "p-cuisine",
    "p-budget",
    "p-style",
  ];
  const PROFILE_FIELDS = [
    "age",
    "weight_kg",
    "height_cm",
    "gender",
    "goal",
    "level",
    "equipment",
    "duration_min",
    "frequency_per_week",
    "limitations",
    "diet_type",
    "cuisine_preference",
    "budget",
    "communication_style",
  ];
  const state = {
    history: [],
    profile: {},
    dailyCalories: [],
    calorieWindowStart: null,
    calorieWindowSize: 7,
    lastSyncAt: null,
    pollTimer: null,
    profileDirty: false,
    profileDirtyTimer: null,
  };
  let sending = false;

  if (!window.hfApi.getToken()) {
    window.location.replace("/login");
    return;
  }

  function escapeHtml(value) {
    return String(value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/\"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  function nowTime() {
    return new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  }

  function countFilledProfileFields(profile) {
    return PROFILE_FIELDS.filter((key) => {
      const value = profile[key];
      return value !== undefined && value !== null && String(value).trim() !== "";
    }).length;
  }

  function countMeaningfulMessages(history, role) {
    return history.filter((item) => item.role === role && String(item.content || "").trim().length > 0).length;
  }

  function setTextWithBump(el, value) {
    if (!el) {
      return;
    }
    const next = String(value);
    if (el.textContent !== next) {
      el.textContent = next;
      el.classList.remove("bump");
      void el.offsetWidth;
      el.classList.add("bump");
    }
  }

  function setProgress(id, value, max) {
    const fill = document.getElementById(id);
    const pct = max <= 0 ? 0 : Math.min(100, Math.round((value / max) * 100));
    fill.style.width = `${pct}%`;
  }

  function extractLatestMacros(history) {
    function readMacrosFromText(text) {
      const source = String(text || "").toLowerCase();
      const macros = { protein: null, carbs: null, fat: null };

      const numberFirst = /(\d+(?:\.\d+)?)\s*g\s*(?:of\s+)?(protein|carbs?|carbohydrates|fat)\b/gi;
      const labelFirst = /(protein|carbs?|carbohydrates|fat)\s*(?:\(|:|=|is|about|approximately)?\s*(\d+(?:\.\d+)?)\s*g\b/gi;

      const assign = (label, rawValue) => {
        const value = Number(rawValue);
        if (Number.isNaN(value)) {
          return;
        }
        const key = label.startsWith("carb") ? "carbs" : label;
        if (macros[key] === null) {
          macros[key] = value;
        }
      };

      let m;
      while ((m = numberFirst.exec(source)) !== null) {
        assign(m[2], m[1]);
      }
      while ((m = labelFirst.exec(source)) !== null) {
        assign(m[1], m[2]);
      }

      return macros;
    }

    const assistantMessages = history.filter((item) => item.role === "assistant").slice().reverse();
    for (const item of assistantMessages) {
      const text = String(item.content || "");
      if (!text.trim()) {
        continue;
      }

      const parsed = readMacrosFromText(text);
      const { protein, carbs, fat } = parsed;

      if (protein !== null && carbs !== null && fat !== null) {
        return {
          protein,
          carbs,
          fat,
        };
      }
    }

    return null;
  }

  function updateStats() {
    const userMessages = countMeaningfulMessages(state.history, "user");
    const assistantMessages = countMeaningfulMessages(state.history, "assistant");
    const messageCount = userMessages + assistantMessages;
    const profileCount = countFilledProfileFields(state.profile);
    setTextWithBump(document.getElementById("statMessages"), messageCount);
    setTextWithBump(document.getElementById("statProfile"), `${profileCount}/${PROFILE_FIELDS.length}`);
    document.getElementById("statSync").textContent = state.lastSyncAt || "-";
  }

  function renderAnalytics(analytics) {
    const el = document.getElementById("analyticsSummary");
    if (!el) {
      return;
    }

    if (!analytics || !analytics.entries) {
      el.textContent = "No progress analytics yet.";
      return;
    }

    const lines = [
      `Entries: ${analytics.entries}`,
      `Consistency: ${analytics.consistency_score}%`,
      `Weight trend: ${analytics.weight_trend}`,
      `Strength trend: ${analytics.strength_trend}`,
      `Calories intake total: ${analytics.calories_logged_total || 0}`,
      `Calories burned total: ${analytics.calories_burned_total || 0}`,
      `Avg intake: ${analytics.calories_logged_average || 0}`,
      `Plateau: ${analytics.plateau_detected ? "yes" : "no"}`,
    ];

    if (Array.isArray(analytics.insights) && analytics.insights.length) {
      lines.push(`Insight: ${analytics.insights[0]}`);
    }
    el.textContent = lines.join(" | ");
  }

  function renderDailyCaloriesChart(daily) {
    const chartEl = document.getElementById("calorieChart");
    const prevBtn = document.getElementById("calPrevBtn");
    const nextBtn = document.getElementById("calNextBtn");
    const rangeLabel = document.getElementById("calRangeLabel");
    if (!chartEl) {
      return;
    }

    const allRows = Array.isArray(daily) ? daily : [];
    const windowSize = state.calorieWindowSize || 7;
    const maxStart = Math.max(0, allRows.length - windowSize);
    if (state.calorieWindowStart === null || state.calorieWindowStart > maxStart) {
      state.calorieWindowStart = maxStart;
    }

    const start = Math.max(0, state.calorieWindowStart || 0);
    const rows = allRows.slice(start, start + windowSize);

    chartEl.innerHTML = "";

    if (rangeLabel) {
      if (rows.length) {
        rangeLabel.textContent = `${String(rows[0].date).slice(5)} to ${String(rows[rows.length - 1].date).slice(5)}`;
      } else {
        rangeLabel.textContent = "No data";
      }
    }
    if (prevBtn) {
      prevBtn.disabled = start <= 0;
    }
    if (nextBtn) {
      nextBtn.disabled = start >= maxStart;
    }

    if (!rows.length) {
      chartEl.innerHTML = '<div class="calorie-empty">No calorie logs yet. Log intake and burned calories to see daily chart.</div>';
      return;
    }

    const peak = Math.max(
      1,
      ...rows.map((d) => Math.max(Number(d.intake || 0), Number(d.burned || 0)))
    );

    rows.forEach((row) => {
      const intake = Math.max(0, Number(row.intake || 0));
      const burned = Math.max(0, Number(row.burned || 0));
      const intakeHeight = Math.max(2, Math.round((intake / peak) * 92));
      const burnedHeight = Math.max(2, Math.round((burned / peak) * 92));
      const dateLabel = String(row.date || "").slice(5);

      const dayEl = document.createElement("div");
      dayEl.className = "calorie-day";
      dayEl.innerHTML = `
        <div class="calorie-bars" title="${row.date}: intake ${intake}, burned ${burned}, net ${Number(row.net || 0)}">
          <div class="calorie-bar intake" style="height:${intakeHeight}px"></div>
          <div class="calorie-bar burned" style="height:${burnedHeight}px"></div>
        </div>
        <div class="calorie-date">${escapeHtml(dateLabel)}</div>
      `;
      chartEl.appendChild(dayEl);
    });
  }

  function updateDashboard() {
    const history = state.history;
    const profile = state.profile;
    const profileCount = countFilledProfileFields(profile);
    const userMessages = countMeaningfulMessages(history, "user");
    const assistantMessages = countMeaningfulMessages(history, "assistant");
    const completionPercent = Math.round((profileCount / PROFILE_FIELDS.length) * 100);

    document.getElementById("goalWorkoutsText").textContent = `${userMessages} / 12`;
    document.getElementById("goalCardioText").textContent = `${assistantMessages} / 12`;
    document.getElementById("goalSleepText").textContent = `${completionPercent}%`;

    setProgress("goalWorkouts", userMessages, 12);
    setProgress("goalCardio", assistantMessages, 12);
    setProgress("goalSleep", completionPercent, 100);

    const macroProteinEl = document.getElementById("macroProtein");
    const macroCarbsEl = document.getElementById("macroCarbs");
    const macroFatEl = document.getElementById("macroFat");
    const latestMacros = extractLatestMacros(history);

    if (!latestMacros) {
      macroProteinEl.textContent = "0g";
      macroCarbsEl.textContent = "0g";
      macroFatEl.textContent = "0g";
      macroProteinEl.classList.add("empty");
      macroCarbsEl.classList.add("empty");
      macroFatEl.classList.add("empty");
    } else {
      macroProteinEl.textContent = `${latestMacros.protein}g`;
      macroCarbsEl.textContent = `${latestMacros.carbs}g`;
      macroFatEl.textContent = `${latestMacros.fat}g`;
      macroProteinEl.classList.remove("empty");
      macroCarbsEl.classList.remove("empty");
      macroFatEl.classList.remove("empty");
    }

    const recentListEl = document.getElementById("recentList");
    recentListEl.innerHTML = "";
    const recentUser = history.filter((item) => item.role === "user").slice(-4).reverse();
    if (!recentUser.length) {
      recentListEl.innerHTML = '<div class="activity-item"><div class="activity-title">No activity yet</div><div class="activity-sub">Start chatting to build your history</div></div>';
      return;
    }

    recentUser.forEach((item, index) => {
      const title = escapeHtml((item.content || "").slice(0, 52) || "Message");
      const row = document.createElement("div");
      row.className = "activity-item";
      row.innerHTML = `<div class="activity-title">${title}${title.length >= 52 ? "..." : ""}</div><div class="activity-sub">Recent chat ${index + 1}</div>`;
      recentListEl.appendChild(row);
    });

    renderDailyCaloriesChart(state.dailyCalories);
  }

  function renderMessages(history) {
    messagesEl.innerHTML = "";
    history.forEach((item) => {
      const content = String(item.content || "").trim();
      if (!content) {
        return;
      }
      addMessage(item.role === "assistant" ? "agent" : "user", content, false);
    });
  }

  function setLiveState(online) {
    if (!liveStateEl) {
      return;
    }
    liveStateEl.textContent = online ? "Live" : "Offline";
    liveStateEl.classList.toggle("offline", !online);
  }

  function setStateFromSessionData(data) {
    state.history = Array.isArray(data.history) ? data.history : [];
    state.profile = data.profile || {};
    state.dailyCalories = data?.progress_analytics?.daily_calories || [];
    const maxStart = Math.max(0, state.dailyCalories.length - state.calorieWindowSize);
    if (state.calorieWindowStart === null || state.calorieWindowStart > maxStart) {
      state.calorieWindowStart = maxStart;
    }
    state.lastSyncAt = nowTime();
    renderAnalytics(data.progress_analytics || null);
  }

  function shiftCalorieWindow(step) {
    const maxStart = Math.max(0, state.dailyCalories.length - state.calorieWindowSize);
    const current = state.calorieWindowStart || 0;
    const next = Math.max(0, Math.min(maxStart, current + step));
    if (next === current) {
      return;
    }
    state.calorieWindowStart = next;
    renderDailyCaloriesChart(state.dailyCalories);
  }

  function profileInputFocused() {
    const active = document.activeElement;
    return !!active && PROFILE_INPUT_IDS.includes(active.id);
  }

  function markProfileDirty() {
    state.profileDirty = true;
    if (state.profileDirtyTimer) {
      clearTimeout(state.profileDirtyTimer);
    }
    state.profileDirtyTimer = setTimeout(() => {
      state.profileDirty = false;
      state.profileDirtyTimer = null;
    }, 20000);
  }

  function addMessage(role, text, refreshStats = true) {
    const div = document.createElement("div");
    const isUser = role === "user";
    div.className = `msg ${isUser ? "user" : "agent"}`;
    div.innerHTML = `
      <div class="msg-avatar">${isUser ? "U" : "AI"}</div>
      <div class="msg-content">
        <div class="msg-bubble">${escapeHtml(text).replace(/\n/g, "<br>")}</div>
        <div class="msg-meta">${nowTime()}</div>
      </div>`;
    messagesEl.appendChild(div);
    messagesEl.scrollTop = messagesEl.scrollHeight;
    if (refreshStats) {
      updateStats();
    }
  }

  function getProfile() {
    const limitationsRaw = document.getElementById("p-limitations").value || "";
    const limitations = limitationsRaw
      .split(",")
      .map((x) => x.trim())
      .filter(Boolean);

    const profile = {
      age: Number(document.getElementById("p-age").value) || undefined,
      weight_kg: Number(document.getElementById("p-weight").value) || undefined,
      height_cm: Number(document.getElementById("p-height").value) || undefined,
      gender: document.getElementById("p-gender").value || undefined,
      goal: document.getElementById("p-goal").value || undefined,
      level: document.getElementById("p-level").value || undefined,
      equipment: document.getElementById("p-equipment").value || undefined,
      duration_min: Number(document.getElementById("p-duration").value) || undefined,
      frequency_per_week: Number(document.getElementById("p-frequency").value) || undefined,
      limitations: limitations.length ? limitations : undefined,
      diet_type: document.getElementById("p-diet").value || undefined,
      cuisine_preference: document.getElementById("p-cuisine").value || undefined,
      budget: document.getElementById("p-budget").value || undefined,
      communication_style: document.getElementById("p-style").value || undefined,
    };

    Object.keys(profile).forEach((key) => {
      if (profile[key] === undefined || profile[key] === "") {
        delete profile[key];
      }
    });

    return profile;
  }

  function setProfile(profile, { force = false } = {}) {
    if (!force && (state.profileDirty || profileInputFocused())) {
      return;
    }

    document.getElementById("p-age").value = profile.age || "";
    document.getElementById("p-weight").value = profile.weight_kg || "";
    document.getElementById("p-height").value = profile.height_cm || "";
    document.getElementById("p-gender").value = profile.gender || "";
    document.getElementById("p-goal").value = profile.goal || "";
    document.getElementById("p-level").value = profile.level || "";
    document.getElementById("p-equipment").value = profile.equipment || "";
    document.getElementById("p-duration").value = profile.duration_min || "";
    document.getElementById("p-frequency").value = profile.frequency_per_week || "";
    document.getElementById("p-limitations").value = Array.isArray(profile.limitations)
      ? profile.limitations.join(", ")
      : profile.limitations || "";
    document.getElementById("p-diet").value = profile.diet_type || "";
    document.getElementById("p-cuisine").value = profile.cuisine_preference || "";
    document.getElementById("p-budget").value = profile.budget || "";
    document.getElementById("p-style").value = profile.communication_style || "";
  }

  async function checkHealth() {
    const { response } = await window.hfApi.request("/api/health");
    if (response.ok) {
      statusDotEl.classList.remove("error");
      statusTextEl.textContent = "Backend connected";
      setLiveState(true);
    } else {
      statusDotEl.classList.add("error");
      statusTextEl.textContent = "Backend offline";
      setLiveState(false);
    }
  }

  async function refreshSessionData({ renderChat = false, syncProfile = false } = {}) {
    const sessionRes = await window.hfApi.request("/api/session/history");
    if (!sessionRes.response.ok) {
      setLiveState(false);
      return false;
    }

    setLiveState(true);
    setStateFromSessionData(sessionRes.data || {});
    if (syncProfile) {
      setProfile(state.profile, { force: true });
    }
    if (renderChat) {
      renderMessages(state.history);
    }
    updateDashboard();
    updateStats();
    return true;
  }

  function startLiveSync() {
    if (state.pollTimer) {
      clearInterval(state.pollTimer);
    }
    state.pollTimer = setInterval(() => {
      refreshSessionData();
    }, 12000);
  }

  async function loadSession() {
    const me = await window.hfApi.request("/api/auth/me");
    if (!me.response.ok) {
      window.hfApi.clearAuth();
      window.location.replace("/login");
      return;
    }

    document.getElementById("activeUser").textContent = me.data.username;

    const loaded = await refreshSessionData({ renderChat: true, syncProfile: true });
    if (!loaded) {
      addMessage("agent", "Failed to load your saved session.");
      return;
    }

    if (!state.history.length) {
      addMessage("agent", "Welcome. Your chat and profile save automatically to your account.");
    }

    startLiveSync();
  }

  async function sendMessage(text = null) {
    const raw = text ?? inputEl.value;
    const message = raw.trim();
    if (!message || sending) {
      return;
    }

    sending = true;
    sendBtn.disabled = true;

    addMessage("user", message);
    state.history.push({ role: "user", content: message });
    updateDashboard();
    updateStats();
    inputEl.value = "";
    inputEl.style.height = "auto";

    const { response, data } = await window.hfApi.request("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        message,
        user_profile: getProfile(),
      }),
    });

    if (!response.ok) {
      addMessage("agent", data?.detail || "Failed to send message.");
      state.history.push({ role: "assistant", content: data?.detail || "Failed to send message." });
    } else {
      const reply = data.reply || "No response received.";
      addMessage("agent", reply);
      state.history.push({ role: "assistant", content: reply });
      await refreshSessionData();
    }

    sending = false;
    sendBtn.disabled = false;
    inputEl.focus();
  }

  async function saveProfile() {
    const profile = getProfile();

    const { response, data } = await window.hfApi.request("/api/profile", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ profile }),
    });

    if (!response.ok) {
      addMessage("agent", data?.detail || "Failed to save profile.");
      return;
    }

    addMessage("agent", "Profile saved successfully.");
    state.profile = profile;
    state.profileDirty = false;
    if (state.profileDirtyTimer) {
      clearTimeout(state.profileDirtyTimer);
      state.profileDirtyTimer = null;
    }
    if (profile.communication_style) {
      await window.hfApi.request("/api/preferences", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ communication_style: profile.communication_style }),
      });
    }
    await refreshSessionData({ syncProfile: true });
    updateStats();
  }

  function parseProgressValue(metric, raw) {
    const text = String(raw || "").trim();
    if (metric === "workout_completed") {
      return text.toLowerCase() === "true" || text === "1" || text.toLowerCase() === "yes";
    }
    const n = Number(text);
    if (!Number.isNaN(n)) {
      return n;
    }
    return text;
  }

  async function logProgress() {
    const metric = document.getElementById("progressMetric")?.value;
    const rawValue = document.getElementById("progressValue")?.value;
    if (!metric || !String(rawValue || "").trim()) {
      addMessage("agent", "Please select a metric and value before logging progress.");
      return;
    }

    const payload = {
      metric,
      value: parseProgressValue(metric, rawValue),
    };

    const { response, data } = await window.hfApi.request("/api/progress/log", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });

    if (!response.ok) {
      addMessage("agent", data?.detail || "Failed to log progress.");
      return;
    }

    addMessage("agent", `Progress logged: ${metric} = ${payload.value}`);
    renderAnalytics(data.analytics || null);
    await refreshSessionData();
  }

  async function createGoal() {
    const title = document.getElementById("goalTitle")?.value?.trim();
    const metric = document.getElementById("goalMetric")?.value?.trim();
    const currentValue = Number(document.getElementById("goalCurrent")?.value);
    const targetValue = Number(document.getElementById("goalTarget")?.value);

    if (!title || !metric || Number.isNaN(currentValue) || Number.isNaN(targetValue)) {
      addMessage("agent", "Please fill title, metric, current value, and target value.");
      return;
    }

    const { response, data } = await window.hfApi.request("/api/goals", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        title,
        metric,
        current_value: currentValue,
        target_value: targetValue,
      }),
    });

    if (!response.ok) {
      addMessage("agent", data?.detail || "Failed to create goal.");
      return;
    }

    addMessage("agent", `Goal created: ${data.goal?.title || title}`);
    await refreshSessionData();
  }

  async function exportPlan() {
    const { response, data } = await window.hfApi.request("/api/export/plan");
    if (!response.ok) {
      addMessage("agent", "Failed to export plan.");
      return;
    }

    const text = data?.text || "No export content available.";
    const blob = new Blob([text], { type: "text/plain" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "apex-plan-export.txt";
    a.click();
    URL.revokeObjectURL(url);
    addMessage("agent", "Plan export generated.");
  }

  async function clearConversation() {
    const { response } = await window.hfApi.request("/api/session", {
      method: "DELETE",
    });

    if (!response.ok) {
      addMessage("agent", "Failed to clear conversation.");
      return;
    }

    messagesEl.innerHTML = "";
    addMessage("agent", "Conversation cleared.");
    state.history = [{ role: "assistant", content: "Conversation cleared." }];
    updateDashboard();
    updateStats();
  }

  async function logout() {
    await window.hfApi.request("/api/auth/logout", { method: "POST" });
    window.hfApi.clearAuth();
    window.location.replace("/login");
  }

  document.querySelectorAll(".chip").forEach((chip) => {
    chip.addEventListener("click", () => sendMessage(chip.textContent || ""));
  });

  sendBtn.addEventListener("click", () => sendMessage());

  inputEl.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      sendMessage();
    }
  });

  inputEl.addEventListener("input", () => {
    inputEl.style.height = "auto";
    inputEl.style.height = Math.min(160, inputEl.scrollHeight) + "px";
  });

  document.getElementById("saveProfileBtn").addEventListener("click", saveProfile);
  document.getElementById("clearChatBtn").addEventListener("click", clearConversation);
  document.getElementById("logoutBtn").addEventListener("click", logout);
  document.getElementById("calPrevBtn")?.addEventListener("click", () => shiftCalorieWindow(-state.calorieWindowSize));
  document.getElementById("calNextBtn")?.addEventListener("click", () => shiftCalorieWindow(state.calorieWindowSize));
  PROFILE_INPUT_IDS.forEach((id) => {
    const el = document.getElementById(id);
    if (!el) {
      return;
    }
    el.addEventListener("input", markProfileDirty);
    el.addEventListener("change", markProfileDirty);
  });
  document.getElementById("logProgressBtn")?.addEventListener("click", logProgress);
  document.getElementById("createGoalBtn")?.addEventListener("click", createGoal);
  document.getElementById("exportPlanBtn")?.addEventListener("click", exportPlan);
  window.addEventListener("beforeunload", () => {
    if (state.pollTimer) {
      clearInterval(state.pollTimer);
    }
  });

  checkHealth();
  loadSession();
})();
