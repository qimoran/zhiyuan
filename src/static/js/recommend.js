(function () {
  const state = {
    step: 0,
    categories: [],
    degreeTypes: [],
    studyModes: [],
    schoolLevels: [],
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
  const suggestions = document.querySelector("[data-category-suggestions]");
  const totalScoreDisplay = document.querySelector("[data-total-score-display]");

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
    if (keyword.length < 3) {
      suggestions.classList.remove("open");
      suggestions.innerHTML = "";
      return;
    }
    const matches = state.categories
      .filter((item) => item.includes(keyword))
      .slice(0, 12);
    suggestions.innerHTML = matches
      .map((item) => `<button type="button" data-category="${App.escapeHtml(item)}">${App.escapeHtml(item)}</button>`)
      .join("");
    suggestions.classList.toggle("open", matches.length > 0);
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

  async function handleSubmit(event) {
    event.preventDefault();
    if (!validateCurrentStep()) return;
    const scoreInputs = Array.from(form.querySelectorAll("input[type='number']"));
    if (!scoreInputs.every(validateScoreField)) {
      setStep(1);
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
  categoryInput.addEventListener("input", App.debounce(renderSuggestions, 120));
  suggestions.addEventListener("click", (event) => {
    const button = event.target.closest("[data-category]");
    if (!button) return;
    categoryInput.value = button.dataset.category;
    suggestions.classList.remove("open");
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
