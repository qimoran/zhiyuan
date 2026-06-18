(function () {
  const grid = document.querySelector("[data-university-grid]");
  if (!grid) return;
  const keywordInput = document.querySelector("[data-university-keyword]");
  const levelsEl = document.querySelector("[data-university-levels]");
  const metaEl = document.querySelector("[data-university-meta]");
  const emptyEl = document.querySelector("[data-university-empty]");
  const titleCountEl = document.querySelector("[data-university-title-count]");
  let schoolLevels = [];
  let selectedLevels = new Set();
  let requestId = 0;

  async function init() {
    schoolLevels = await App.fetchJson("/api/metadata/school-levels");
    renderLevels();
    await loadUniversities();
  }

  function renderLevels() {
    levelsEl.innerHTML = schoolLevels
      .map((item) => `
        <label class="choice">
          <input type="checkbox" value="${App.escapeHtml(item.value)}">
          ${App.escapeHtml(item.label)}
        </label>
      `)
      .join("");
  }

  function matchSelectedLevels(item) {
    if (!selectedLevels.size) return true;
    const level = item.school_level || "";
    return Array.from(selectedLevels).some((selected) => level.includes(selected) || selected.includes(level));
  }

  async function loadUniversities() {
    const current = ++requestId;
    metaEl.textContent = "正在加载学校数据...";
    emptyEl.hidden = true;
    try {
      const data = await App.fetchJson(`/api/university/list${App.buildQuery({ limit: 200, keyword: keywordInput.value.trim() })}`);
      if (current !== requestId) return;
      const items = (data.items || []).filter(matchSelectedLevels);
      if (titleCountEl && !keywordInput.value.trim() && selectedLevels.size === 0) {
        titleCountEl.textContent = `重庆地区 ${data.total} 所研招单位候选库。`;
      }
      metaEl.textContent = `共 ${items.length} 所学校`;
      emptyEl.hidden = items.length > 0;
      grid.innerHTML = items.map(renderCard).join("");
    } catch (error) {
      metaEl.textContent = error.message;
      grid.innerHTML = "";
      emptyEl.hidden = false;
    }
  }

  function renderCard(item) {
    return `
      <article class="university-card">
        <h2>${App.escapeHtml(item.university_name)}</h2>
        <span class="tag">${App.escapeHtml(item.school_level || "层次待补充")}</span>
        <p>${App.escapeHtml(item.city || "重庆市")} · ${App.escapeHtml(item.school_type || "类型待补充")}</p>
        <p>招生专业参考数：${App.escapeHtml(item.major_number_reference || "待统计")}</p>
        <a class="card-action" href="/majors?school_id=${encodeURIComponent(item.candidate_school_id || "")}">查看详情 →</a>
      </article>
    `;
  }

  keywordInput.addEventListener("input", App.debounce(loadUniversities, 250));
  levelsEl.addEventListener("change", () => {
    selectedLevels = new Set(Array.from(levelsEl.querySelectorAll("input:checked")).map((item) => item.value));
    loadUniversities();
  });

  init().catch((error) => {
    metaEl.textContent = error.message;
  });
})();
