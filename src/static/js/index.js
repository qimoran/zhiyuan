(function () {
  const statEls = {
    universities: document.querySelector("[data-stat='universities']"),
    majors: document.querySelector("[data-stat='majors']"),
    score_lines: document.querySelector("[data-stat='score_lines']"),
  };
  const rangeEl = document.querySelector("[data-data-range]");
  const footerEl = document.querySelector("[data-footer-stats]");

  function formatCount(value, suffix) {
    if (value === null || value === undefined || value === "") return "暂无";
    return `${Number(value).toLocaleString("zh-CN")} ${suffix}`;
  }

  function formatYears(detail) {
    if (!detail.min_year || !detail.max_year) return "年份范围待入库";
    return detail.min_year === detail.max_year ? `${detail.max_year}` : `${detail.min_year}-${detail.max_year}`;
  }

  async function loadHealth() {
    try {
      const data = await App.fetchJson("/api/health");
      const detail = data.detail || {};
      statEls.universities.textContent = formatCount(detail.universities, "所");
      statEls.majors.textContent = formatCount(detail.majors, "个");
      statEls.score_lines.textContent = formatCount(detail.score_lines, "条");
      const years = formatYears(detail);
      rangeEl.textContent = `当前数据库覆盖 ${years} 年数据，包含 ${formatCount(detail.enrollment_plans, "条")}招生计划。`;
      footerEl.textContent = `数据库统计：学校 ${formatCount(detail.universities, "所")} / 专业方向 ${formatCount(detail.majors, "个")} / 分数线 ${formatCount(detail.score_lines, "条")} / 数据年份 ${years}`;
    } catch (error) {
      Object.values(statEls).forEach((el) => {
        if (el) el.textContent = "读取失败";
      });
      rangeEl.textContent = "数据库统计暂不可用，请确认 Docker 和 MySQL 服务已启动。";
      footerEl.textContent = "数据库统计暂不可用，请稍后刷新。";
    }
  }

  loadHealth();
})();
