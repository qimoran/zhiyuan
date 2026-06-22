(function () {
  const table = document.querySelector("[data-major-table]");
  if (!table) return;

  const state = {
    schools: [],
    categories: [],
    degreeTypes: [],
    studyModes: [],
    rows: [],
    total: 0,
    offset: 0,
    limit: 50,
    sortKey: "",
    sortDir: 1,
  };

  const schoolSelect = document.querySelector("[data-major-school]");
  const categorySelect = document.querySelector("[data-major-category]");
  const keywordInput = document.querySelector("[data-major-keyword]");
  const degreeSelect = document.querySelector("[data-major-degree]");
  const studySelect = document.querySelector("[data-major-study]");
  const metaEl = document.querySelector("[data-major-meta]");
  const pageEl = document.querySelector("[data-major-page]");
  const prevBtn = document.querySelector("[data-major-prev]");
  const nextBtn = document.querySelector("[data-major-next]");
  const emptyEl = document.querySelector("[data-major-empty]");

  async function init() {
    const [schools, degreeTypes, studyModes] = await Promise.all([
      App.fetchJson("/api/university/list?limit=200"),
      App.fetchJson("/api/metadata/degree-types"),
      App.fetchJson("/api/metadata/study-modes"),
    ]);
    state.schools = schools.items || [];
    state.degreeTypes = degreeTypes || [];
    state.studyModes = studyModes || [];
    renderFilters();
    const params = new URLSearchParams(window.location.search);
    if (params.get("school_id")) schoolSelect.value = params.get("school_id");
    await loadCategories();
    loadMajors();
  }

  function renderFilters() {
    schoolSelect.innerHTML = `<option value="">全部学校</option>${state.schools
      .map((item) => `<option value="${App.escapeHtml(item.candidate_school_id)}">${App.escapeHtml(item.university_name)}</option>`)
      .join("")}`;
    categorySelect.innerHTML = `<option value="">全部专业门类</option>${state.categories
      .map((item) => `<option value="${App.escapeHtml(item)}">${App.escapeHtml(item)}</option>`)
      .join("")}`;
    degreeSelect.innerHTML = renderSelectOptions("全部学位类型", state.degreeTypes);
    studySelect.innerHTML = renderSelectOptions("全部学习方式", state.studyModes);
  }

  async function loadCategories() {
    const selectedCategory = categorySelect.value;
    categorySelect.disabled = true;
    categorySelect.innerHTML = `<option value="">正在加载专业门类...</option>`;
    try {
      const data = await App.fetchJson(`/api/metadata/major-categories${App.buildQuery({ school_id: schoolSelect.value })}`);
      state.categories = (data.combined || []).filter(isReadableCategory);
      renderCategoryOptions(selectedCategory);
    } catch (error) {
      state.categories = [];
      renderCategoryOptions("");
      App.showToast(error.message);
    } finally {
      categorySelect.disabled = false;
    }
  }

  function renderCategoryOptions(selectedCategory) {
    categorySelect.innerHTML = `<option value="">全部专业门类</option>${state.categories
      .map((item) => {
        const selected = item === selectedCategory ? " selected" : "";
        return `<option value="${App.escapeHtml(item)}"${selected}>${App.escapeHtml(item)}</option>`;
      })
      .join("")}`;
    if (selectedCategory && categorySelect.value !== selectedCategory) {
      categorySelect.value = "";
    }
  }

  function renderSelectOptions(defaultLabel, items) {
    return `<option value="">${App.escapeHtml(defaultLabel)}</option>${items
      .map((item) => `<option value="${App.escapeHtml(item.value)}">${App.escapeHtml(item.label)}</option>`)
      .join("")}`;
  }

  function isReadableCategory(value) {
    const text = String(value || "").trim();
    return /[\u4e00-\u9fff]/.test(text) && !/[\u00a0-\u00ff\ufffd]/.test(text);
  }

  function buildParams() {
    return {
      limit: state.limit,
      offset: state.offset,
      school_id: schoolSelect.value,
      major_category: categorySelect.value,
      degree_type: degreeSelect.value,
      study_mode: studySelect.value,
      keyword: keywordInput.value.trim(),
    };
  }

  async function loadMajors() {
    metaEl.textContent = "正在加载专业数据...";
    try {
      const data = await App.fetchJson(`/api/major/list${App.buildQuery(buildParams())}`);
      state.rows = data.items || [];
      state.total = data.total || 0;
      renderTable();
    } catch (error) {
      state.rows = [];
      state.total = 0;
      metaEl.textContent = error.message;
      renderTable();
    }
  }

  function sortedRows() {
    const rows = [...state.rows];
    if (!state.sortKey) return rows;
    return rows.sort((a, b) => String(a[state.sortKey] || "").localeCompare(String(b[state.sortKey] || ""), "zh-CN") * state.sortDir);
  }

  function renderMetaPill(kind, value, label) {
    const classMap = {
      degree: {
        academic: "major-pill-degree-academic",
        professional: "major-pill-degree-professional",
      },
      study: {
        full_time: "major-pill-study-full",
        part_time: "major-pill-study-part",
      },
    };
    const toneClass = (classMap[kind] && classMap[kind][value]) || "major-pill-neutral";
    return `<span class="major-pill ${toneClass}">${App.escapeHtml(label || value || "未填写")}</span>`;
  }

  function renderTable() {
    const rows = sortedRows();
    emptyEl.hidden = rows.length > 0;
    table.innerHTML = rows
      .map((item) => `
        <tr>
          <td>${App.escapeHtml(item.university_name)}</td>
          <td>${App.escapeHtml(item.department_name)}</td>
          <td>${App.escapeHtml(item.major_name)}</td>
          <td>${renderMetaPill("degree", item.degree_type, App.labelDegree(item.degree_type))}</td>
          <td>${renderMetaPill("study", item.study_mode, App.labelStudyMode(item.study_mode))}</td>
          <td>${App.escapeHtml(item.research_direction || "未区分研究方向")}</td>
        </tr>
      `)
      .join("");
    const currentPage = Math.floor(state.offset / state.limit) + 1;
    const totalPages = Math.max(1, Math.ceil(state.total / state.limit));
    metaEl.textContent = `共 ${state.total} 条，当前显示 ${rows.length} 条`;
    pageEl.textContent = `${currentPage} / ${totalPages}`;
    prevBtn.disabled = state.offset <= 0;
    nextBtn.disabled = state.offset + state.limit >= state.total;
  }

  function resetAndLoad() {
    state.offset = 0;
    loadMajors();
  }

  schoolSelect.addEventListener("change", async () => {
    await loadCategories();
    resetAndLoad();
  });
  categorySelect.addEventListener("change", resetAndLoad);
  keywordInput.addEventListener("input", App.debounce(resetAndLoad, 250));
  degreeSelect.addEventListener("change", resetAndLoad);
  studySelect.addEventListener("change", resetAndLoad);
  prevBtn.addEventListener("click", () => {
    state.offset = Math.max(0, state.offset - state.limit);
    loadMajors();
  });
  nextBtn.addEventListener("click", () => {
    state.offset += state.limit;
    loadMajors();
  });
  document.querySelector("[data-major-reset]").addEventListener("click", async () => {
    schoolSelect.value = "";
    categorySelect.value = "";
    keywordInput.value = "";
    degreeSelect.value = "";
    studySelect.value = "";
    await loadCategories();
    resetAndLoad();
  });
  document.querySelectorAll("[data-sort]").forEach((header) => {
    header.addEventListener("click", () => {
      const key = header.dataset.sort;
      state.sortDir = state.sortKey === key ? -state.sortDir : 1;
      state.sortKey = key;
      renderTable();
    });
  });

  init().catch((error) => {
    metaEl.textContent = error.message;
  });
})();
