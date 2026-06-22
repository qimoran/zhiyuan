(function () {
  const state = {
    step: 0,
    categories: [],
    degreeTypes: [],
    studyModes: [],
    schoolLevels: [],
    agenticSessionId: "",
  };

  const form = document.querySelector("#recommendForm");
  if (!form) return;

  const stepEls = Array.from(document.querySelectorAll("[data-step]"));
  const stepList = Array.from(document.querySelectorAll("[data-step-list] li"));
  const stepTitle = document.querySelector("[data-step-title]");
  const progress = document.querySelector("[data-form-progress]");
  const prevBtn = document.querySelector("[data-prev-step]");
  const nextBtn = document.querySelector("[data-next-step]");
  const submitBtn = document.querySelector("[data-submit-button]");
  const formError = document.querySelector("[data-form-error]");
  const categoryInput = form.elements.major_category;
  const categorySuggestions = document.querySelector("[data-category-suggestions]");
  const majorNameInput = form.elements.major_name;
  const majorNameSuggestions = document.querySelector("[data-major-suggestions]");
  const totalScoreDisplay = document.querySelector("[data-total-score-display]");
  const agenticForm = document.querySelector("[data-agentic-form]");
  const agenticMessages = document.querySelector("[data-agentic-messages]");
  const agenticInput = agenticForm?.elements.agentic_message;
  const agenticSend = document.querySelector("[data-agentic-send]");
  const agenticReset = document.querySelector("[data-agentic-reset]");
  const agenticError = document.querySelector("[data-agentic-error]");
  const agenticResult = document.querySelector("[data-agentic-result]");

  const stepTitles = ["步骤 1 / 3：基本信息", "步骤 2 / 3：成绩输入", "步骤 3 / 3：偏好设置"];

  function setStep(nextStep) {
    state.step = Math.max(0, Math.min(2, nextStep));
    stepEls.forEach((el, index) => el.classList.toggle("active", index === state.step));
    stepList.forEach((el, index) => el.classList.toggle("active", index === state.step));
    stepTitle.textContent = stepTitles[state.step];
    progress.style.width = `${(state.step + 1) * 33.33}%`;
    prevBtn.classList.toggle("hidden", state.step === 0);
    nextBtn.classList.toggle("hidden", state.step === 2);
    submitBtn.classList.toggle("hidden", state.step !== 2);
    formError.textContent = "";
  }

  function optionHtml(items, selectedValue) {
    return items
      .map((item) => {
        const value = typeof item === "string" ? item : item.value;
        const label = typeof item === "string" ? item : item.label;
        const selected = selectedValue === value ? " selected" : "";
        return `<option value="${App.escapeHtml(value)}"${selected}>${App.escapeHtml(label)}</option>`;
      })
      .join("");
  }

  async function loadMetadata() {
    const [categories, degreeTypes, studyModes, schoolLevels] = await Promise.all([
      App.fetchJson("/api/metadata/major-categories"),
      App.fetchJson("/api/metadata/degree-types"),
      App.fetchJson("/api/metadata/study-modes"),
      App.fetchJson("/api/metadata/school-levels"),
    ]);
    state.categories = categories.combined || [];
    state.degreeTypes = degreeTypes || [];
    state.studyModes = studyModes || [];
    state.schoolLevels = schoolLevels || [];

    document.querySelector("[data-degree-types]").innerHTML = optionHtml(state.degreeTypes, "professional");
    document.querySelector("[data-study-modes]").innerHTML = optionHtml(state.studyModes, "full_time");
    renderSchoolLevels();
  }

  function renderSchoolLevels() {
    const target = document.querySelector("[data-school-levels]");
    target.innerHTML = state.schoolLevels
      .map((item) => {
        const checked = item.value.includes("双一流") || item.value.includes("普通院校") ? " checked" : "";
        return `
          <label class="choice">
            <input type="checkbox" name="preferred_school_levels" value="${App.escapeHtml(item.value)}"${checked}>
            ${App.escapeHtml(item.label)}
          </label>
        `;
      })
      .join("");
  }

  function renderSuggestions() {
    const keyword = categoryInput.value.trim();
    if (keyword.length < 1) {
      categorySuggestions.classList.remove("open");
      categorySuggestions.innerHTML = "";
      return;
    }

    App.fetchJson(`/api/metadata/search-major-categories?keyword=${encodeURIComponent(keyword)}&limit=12`)
      .then((matches) => {
        categorySuggestions.innerHTML = matches
          .map((item) => `<button type="button" data-category="${App.escapeHtml(item)}">${App.escapeHtml(item)}</button>`)
          .join("");
        categorySuggestions.classList.toggle("open", matches.length > 0);
      })
      .catch(() => {
        categorySuggestions.classList.remove("open");
        categorySuggestions.innerHTML = "";
      });
  }

  function majorSearchParams(keyword) {
    return {
      keyword,
      limit: 12,
      target_year: form.elements.target_year.value,
      major_category: categoryInput.value.trim(),
      degree_type: form.elements.degree_type.value,
      study_mode: form.elements.study_mode.value,
    };
  }

  function renderMajorNameSuggestions() {
    const keyword = majorNameInput.value.trim();
    if (keyword.length < 1) {
      majorNameSuggestions.classList.remove("open");
      majorNameSuggestions.innerHTML = "";
      return;
    }

    App.fetchJson(`/api/metadata/search-major-names${App.buildQuery(majorSearchParams(keyword))}`)
      .then((matches) => {
        if (!matches.length) {
          majorNameSuggestions.innerHTML = '<div class="autocomplete-empty">未找到本地专业数据</div>';
          majorNameSuggestions.classList.add("open");
          return;
        }
        majorNameSuggestions.innerHTML = matches
          .map((item) => {
            const code = item.major_code ? `(${App.escapeHtml(item.major_code)})` : "";
            const category = item.major_category ? ` · ${App.escapeHtml(item.major_category)}` : "";
            const plan = item.total_plan ? ` · 招生计划 ${App.escapeHtml(item.total_plan)} 人` : "";
            return `
              <button
                type="button"
                data-major-name="${App.escapeHtml(item.major_name)}"
                data-major-category="${App.escapeHtml(item.major_category || "")}"
              >
                <strong>${App.escapeHtml(item.major_name)} ${code}</strong>
                <small>${App.escapeHtml(item.match_count || 0)} 所学校${category}${plan}</small>
              </button>
            `;
          })
          .join("");
        majorNameSuggestions.classList.toggle("open", matches.length > 0);
      })
      .catch(() => {
        majorNameSuggestions.classList.remove("open");
        majorNameSuggestions.innerHTML = "";
      });
  }

  function validateScoreField(input) {
    const field = input.closest(".field");
    const small = field.querySelector("small");
    const min = Number(input.min);
    const max = Number(input.max);
    const value = Number(input.value);
    const invalid = input.value === "" || Number.isNaN(value) || value < min || value > max;
    field.classList.toggle("error", invalid);
    if (small) small.textContent = invalid ? `请输入 ${min}-${max} 范围内的分数` : "";
    return !invalid;
  }

  function scoreValue(fieldName) {
    const value = Number(form.elements[fieldName].value);
    return Number.isNaN(value) ? 0 : value;
  }

  function calculateTotalScore() {
    return (
      scoreValue("politics_score") +
      scoreValue("english_score") +
      scoreValue("subject_one_score") +
      scoreValue("subject_two_score")
    );
  }

  function updateTotalScore() {
    if (totalScoreDisplay) totalScoreDisplay.textContent = String(calculateTotalScore());
  }

  function validateCurrentStep() {
    formError.textContent = "";
    const current = stepEls[state.step];
    const requiredFields = Array.from(current.querySelectorAll("[required]"));
    const missing = requiredFields.find((field) => !String(field.value || "").trim());
    if (missing) {
      formError.textContent = "请先填写当前步骤的必填项。";
      missing.focus();
      return false;
    }
    if (state.step === 1) {
      const scoreInputs = Array.from(current.querySelectorAll("input[type='number']"));
      return scoreInputs.every(validateScoreField);
    }
    return true;
  }

  function buildPayload() {
    const selectedLevels = Array.from(form.querySelectorAll("input[name='preferred_school_levels']:checked")).map(
      (item) => item.value
    );
    return {
      target_year: Number(form.elements.target_year.value),
      province: "重庆",
      major_category: form.elements.major_category.value.trim(),
      major_name: form.elements.major_name.value.trim(),
      degree_type: form.elements.degree_type.value,
      study_mode: form.elements.study_mode.value,
      preferred_school_levels: selectedLevels,
      bucket_limit: Number(form.elements.bucket_limit.value),
      total_score: calculateTotalScore(),
      politics_score: Number(form.elements.politics_score.value),
      english_score: Number(form.elements.english_score.value),
      subject_one_score: Number(form.elements.subject_one_score.value),
      subject_two_score: Number(form.elements.subject_two_score.value),
    };
  }

  function addAgenticMessage(role, content) {
    if (!agenticMessages) return;
    const message = document.createElement("div");
    message.className = `agentic-message ${role}`;
    message.textContent = content;
    agenticMessages.appendChild(message);
    agenticMessages.scrollTop = agenticMessages.scrollHeight;
  }

  function setAgenticLoading(loading) {
    if (agenticSend) {
      agenticSend.disabled = loading;
      agenticSend.textContent = loading ? "分析中..." : "发送";
    }
    if (agenticInput) agenticInput.disabled = loading;
  }

  function applyAgenticProfile(profile) {
    if (!profile) return;
    if (profile.target_major && !majorNameInput.value) majorNameInput.value = profile.target_major;
    if (profile.major_category && !categoryInput.value) categoryInput.value = profile.major_category;
    if (profile.degree_type && form.elements.degree_type) form.elements.degree_type.value = profile.degree_type;
    if (profile.study_mode && form.elements.study_mode) form.elements.study_mode.value = profile.study_mode;
    if (profile.school_level_preference) {
      form.querySelectorAll("input[name='preferred_school_levels']").forEach((item) => {
        item.checked = item.value.includes(profile.school_level_preference);
      });
    }
  }

  function agenticTierLabel(key) {
    return { rush: "冲刺", stable: "稳妥", safe: "保底" }[key] || key;
  }

  function renderAgenticResult(data) {
    if (!agenticResult || !data?.recommendation_result) return;
    const result = data.recommendation_result;
    const request = data.recommendation_request || {};
    const groups = result.recommendations || {};
    const tiers = ["rush", "stable", "safe"];
    const totalCount = tiers.reduce((sum, key) => sum + ((groups[key] || []).length), 0);
    if (!totalCount) {
      agenticResult.hidden = false;
      agenticResult.innerHTML = `
        <h3>对话推荐结果</h3>
        <p class="muted">当前条件没有匹配到推荐院校，可以放宽学校层次或专业关键词后重试。</p>
      `;
      return;
    }

    sessionStorage.setItem("recommendationRequest", JSON.stringify(request));
    sessionStorage.setItem("recommendationResult", JSON.stringify(result));
    sessionStorage.removeItem("latestReport");
    sessionStorage.removeItem("reportGenerationError");

    agenticResult.hidden = false;
    agenticResult.innerHTML = `
      <div class="agentic-result-head">
        <div>
          <h3>对话推荐结果</h3>
          <p>专业：${App.escapeHtml(request.major_name || request.major_category || "未填写")} · 总分 ${App.escapeHtml(request.total_score || "")}</p>
        </div>
        <a class="btn btn-blue" href="/result">查看完整结果</a>
      </div>
      <div class="agentic-result-grid">
        ${tiers
          .map((tier) => {
            const items = groups[tier] || [];
            return `
              <article class="agentic-tier ${tier}">
                <h4>${App.escapeHtml(agenticTierLabel(tier))}</h4>
                ${
                  items.length
                    ? items
                        .slice(0, 3)
                        .map(
                          (item) => `
                            <div class="agentic-school">
                              <strong>${App.escapeHtml(item.university_name || "未知院校")}</strong>
                              <span>${App.escapeHtml(item.major_name || request.major_name || "目标专业")} · 复试线 ${App.escapeHtml(item.score_line || "暂无")} · 分差 ${App.escapeHtml(item.score_diff ?? "暂无")}</span>
                              <small>${App.escapeHtml(item.evidence_summary || item.reason || "暂无资料摘要")}</small>
                            </div>
                          `
                        )
                        .join("")
                    : '<p class="muted">暂无匹配院校</p>'
                }
              </article>
            `;
          })
          .join("")}
      </div>
    `;
  }

  async function handleAgenticSubmit(event) {
    event.preventDefault();
    const message = agenticInput?.value.trim();
    if (!message) return;
    if (agenticError) agenticError.textContent = "";
    addAgenticMessage("user", message);
    agenticInput.value = "";
    setAgenticLoading(true);
    try {
      const data = await App.fetchJson("/api/conversation/chat", {
        method: "POST",
        body: JSON.stringify({
          session_id: state.agenticSessionId || undefined,
          message,
        }),
      });
      state.agenticSessionId = data.session_id || state.agenticSessionId;
      addAgenticMessage("assistant", data.response || "已收到。");
      applyAgenticProfile(data.user_profile);
      renderAgenticResult(data);
    } catch (error) {
      if (agenticError) agenticError.textContent = error.message;
      addAgenticMessage("assistant", "对话推荐暂时不可用，你可以直接填写下方表单生成推荐。");
    } finally {
      setAgenticLoading(false);
      agenticInput?.focus();
    }
  }

  function resetAgenticConversation() {
    state.agenticSessionId = "";
    if (agenticMessages) {
      agenticMessages.innerHTML = '<div class="agentic-message assistant">你好，我可以通过对话帮你完成择校推荐。请先告诉我你的本科学校和本科专业。</div>';
    }
    if (agenticResult) {
      agenticResult.hidden = true;
      agenticResult.innerHTML = "";
    }
    if (agenticError) agenticError.textContent = "";
    if (agenticInput) {
      agenticInput.value = "";
      agenticInput.focus();
    }
  }

  async function handleSubmit(event) {
    event.preventDefault();
    if (!validateCurrentStep()) return;
    const scoreInputs = Array.from(form.querySelectorAll("input[type='number']"));
    if (!scoreInputs.every(validateScoreField)) {
      setStep(1);
      return;
    }
    const authState = App.auth.loaded ? App.auth : await App.loadCurrentUser();
    if (!authState.authenticated) {
      App.showToast("请先登录后再查看推荐结果。");
      window.location.href = "/login?next=/recommend";
      return;
    }
    const payload = buildPayload();
    submitBtn.disabled = true;
    submitBtn.textContent = "正在分析...";
    formError.textContent = "";
    try {
      const result = await App.fetchJson("/api/recommend", {
        method: "POST",
        body: JSON.stringify(payload),
      });
      sessionStorage.setItem("recommendationRequest", JSON.stringify(payload));
      sessionStorage.setItem("recommendationResult", JSON.stringify(result));
      sessionStorage.removeItem("latestReport");
      sessionStorage.removeItem("reportGenerationError");
      window.location.href = "/result";
    } catch (error) {
      formError.textContent = error.message;
    } finally {
      submitBtn.disabled = false;
      submitBtn.textContent = "开始分析";
    }
  }

  prevBtn.addEventListener("click", () => setStep(state.step - 1));
  nextBtn.addEventListener("click", () => {
    if (validateCurrentStep()) setStep(state.step + 1);
  });
  form.addEventListener("submit", handleSubmit);
  agenticForm?.addEventListener("submit", handleAgenticSubmit);
  agenticReset?.addEventListener("click", resetAgenticConversation);
  categoryInput.addEventListener("input", App.debounce(renderSuggestions, 300));
  categorySuggestions.addEventListener("click", (event) => {
    const button = event.target.closest("[data-category]");
    if (!button) return;
    categoryInput.value = button.dataset.category;
    categorySuggestions.classList.remove("open");
  });
  majorNameInput.addEventListener("input", App.debounce(renderMajorNameSuggestions, 300));
  majorNameSuggestions.addEventListener("click", (event) => {
    const button = event.target.closest("[data-major-name]");
    if (!button) return;
    majorNameInput.value = button.dataset.majorName;
    if (button.dataset.majorCategory) categoryInput.value = button.dataset.majorCategory;
    majorNameSuggestions.classList.remove("open");
  });
  form.elements.bucket_limit.addEventListener("input", (event) => {
    document.querySelector("[data-bucket-count]").textContent = event.target.value;
  });
  form.querySelectorAll("input[type='number']").forEach((input) => {
    input.addEventListener("input", () => {
      validateScoreField(input);
      updateTotalScore();
    });
  });

  setStep(0);
  updateTotalScore();
  loadMetadata().catch((error) => {
    formError.textContent = error.message;
  });
})();
