(function () {
  if (typeof echarts === "undefined") {
    document.querySelectorAll(".chart-note").forEach((el) => {
      el.textContent = "ECharts 加载失败，请检查 static/js/vendor/echarts.min.js。";
    });
    return;
  }

  // 主题色，与全站配色保持一致。
  const PALETTE = ["#0f766e", "#d97706", "#2563eb", "#16a34a", "#dc2626", "#7c3aed"];
  const charts = {};

  function getChart(key) {
    const el = document.querySelector(`[data-chart="${key}"]`);
    if (!el) return null;
    if (!charts[key]) {
      charts[key] = echarts.init(el);
    }
    return charts[key];
  }

  function setNote(key, payload) {
    const noteEl = document.querySelector(`[data-note="${key}"]`);
    if (!noteEl) return;
    const parts = [];
    const range = payload && payload.year_range;
    if (range && range.min_year) {
      parts.push(
        range.min_year === range.max_year
          ? `数据年份：${range.min_year}`
          : `数据年份：${range.min_year}–${range.max_year}`
      );
    }
    if (payload && payload.source_note) parts.push(payload.source_note);
    if (payload && Array.isArray(payload.warnings) && payload.warnings.length) {
      parts.push("⚠ " + payload.warnings.join("；"));
    }
    noteEl.textContent = parts.join("　·　");
  }

  function showEmpty(key, payload) {
    const chart = getChart(key);
    if (!chart) return;
    chart.clear();
    const msg = (payload.warnings && payload.warnings[0]) || "暂无数据";
    chart.setOption({
      title: {
        text: msg,
        left: "center",
        top: "center",
        textStyle: { color: "#94a3b8", fontSize: 14, fontWeight: 600 },
      },
    });
    setNote(key, payload);
  }

  function isEmpty(payload) {
    return !payload || !Array.isArray(payload.x_axis) || payload.x_axis.length === 0;
  }

  function baseLineOption(payload) {
    const mainColor = "#f97316";
    const seriesColors = [mainColor, "#0f766e", "#2563eb", "#16a34a", "#dc2626"];
    return {
      color: seriesColors,
      tooltip: {
        trigger: "axis",
        backgroundColor: "#ffffff",
        borderColor: "rgba(15, 23, 42, 0.1)",
        borderWidth: 1,
        textStyle: { color: "#334155" },
        axisPointer: {
          type: "line",
          lineStyle: { color: "rgba(249, 115, 22, 0.45)", type: "dashed" },
        },
      },
      legend: { top: 0, type: "scroll" },
      grid: { top: 48, left: 12, right: 24, bottom: 12, containLabel: true },
      xAxis: {
        type: "category",
        data: payload.x_axis,
        boundaryGap: false,
        axisTick: { show: false },
        axisLine: { lineStyle: { color: "#cbd5e1" } },
        axisLabel: { color: "#64748b" },
      },
      yAxis: {
        type: "value",
        scale: true,
        axisLabel: { color: "#64748b" },
        splitLine: { lineStyle: { color: "#e5e7eb", type: "dashed" } },
      },
      series: payload.series.map((s, index) => {
        const color = seriesColors[index % seriesColors.length];
        return {
          name: s.name,
          type: "line",
          smooth: true,
          connectNulls: true,
          symbol: "circle",
          symbolSize: index === 0 ? 8 : 6,
          showSymbol: true,
          lineStyle: { width: index === 0 ? 3 : 2, color },
          itemStyle: { color, borderColor: "#ffffff", borderWidth: index === 0 ? 2 : 1 },
          emphasis: { focus: "series" },
          data: s.data,
          ...(index === 0
            ? {
                areaStyle: {
                  color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
                    { offset: 0, color: "rgba(249, 115, 22, 0.28)" },
                    { offset: 0.72, color: "rgba(249, 115, 22, 0.08)" },
                    { offset: 1, color: "rgba(249, 115, 22, 0)" },
                  ]),
                },
              }
            : {}),
        };
      }),
    };
  }

  function baseBarOption(payload, rotate) {
    return {
      color: PALETTE,
      tooltip: { trigger: "axis", axisPointer: { type: "shadow" } },
      legend: { top: 0, type: "scroll" },
      grid: { top: 44, left: 12, right: 24, bottom: rotate ? 70 : 24, containLabel: true },
      xAxis: {
        type: "category",
        data: payload.x_axis,
        axisLabel: rotate ? { rotate: 32, interval: 0, fontSize: 11 } : {},
      },
      yAxis: { type: "value" },
      series: payload.series.map((s) => ({ name: s.name, type: "bar", data: s.data })),
    };
  }

  function dualYAxis(leftName, rightName) {
    return [
      {
        type: "value",
        name: leftName,
        scale: true,
        nameTextStyle: { color: PALETTE[0], fontWeight: 700 },
        axisLine: { show: true, lineStyle: { color: PALETTE[0] } },
        axisLabel: { color: "#64748b" },
        splitLine: { lineStyle: { color: "#e5e7eb" } },
      },
      {
        type: "value",
        name: rightName,
        scale: true,
        position: "right",
        nameTextStyle: { color: PALETTE[1], fontWeight: 700 },
        axisLine: { show: true, lineStyle: { color: PALETTE[1] } },
        axisLabel: { color: "#64748b" },
        splitLine: { show: false },
      },
    ];
  }

  function dualAxisLineOption(payload) {
    const leftName = payload.series[0] ? payload.series[0].name : "数值";
    const rightName = payload.series[1] ? payload.series[1].name : "数量";
    return {
      color: PALETTE,
      tooltip: { trigger: "axis" },
      legend: { top: 0, type: "scroll" },
      grid: { top: 52, left: 12, right: 42, bottom: 12, containLabel: true },
      xAxis: { type: "category", data: payload.x_axis, boundaryGap: false },
      yAxis: dualYAxis(leftName, rightName),
      series: payload.series.map((s, index) => ({
        name: s.name,
        type: "line",
        yAxisIndex: index === 0 ? 0 : 1,
        smooth: true,
        connectNulls: true,
        symbolSize: 7,
        data: s.data,
      })),
    };
  }

  function dualAxisBarOption(payload, rotate) {
    const leftName = payload.series[0] ? payload.series[0].name : "数值";
    const rightName = payload.series[1] ? payload.series[1].name : "数量";
    return {
      color: PALETTE,
      tooltip: { trigger: "axis", axisPointer: { type: "shadow" } },
      legend: { top: 0, type: "scroll" },
      grid: { top: 52, left: 12, right: 42, bottom: rotate ? 70 : 24, containLabel: true },
      xAxis: {
        type: "category",
        data: payload.x_axis,
        axisLabel: rotate ? { rotate: 32, interval: 0, fontSize: 11 } : {},
      },
      yAxis: dualYAxis(leftName, rightName),
      series: payload.series.map((s, index) => ({
        name: s.name,
        type: "bar",
        yAxisIndex: index === 0 ? 0 : 1,
        data: s.data,
      })),
    };
  }

  function pieOption(payload) {
    const pieData = (payload.series[0] && payload.series[0].pie_data) || [];
    return {
      color: PALETTE,
      tooltip: { trigger: "item", formatter: "{b}：{c} 所（{d}%）" },
      legend: { type: "scroll", bottom: 0 },
      series: [
        {
          name: payload.series[0] ? payload.series[0].name : "数量",
          type: "pie",
          radius: ["38%", "66%"],
          center: ["50%", "44%"],
          avoidLabelOverlap: true,
          itemStyle: { borderColor: "#fff", borderWidth: 2 },
          label: { formatter: "{b}\n{c} 所" },
          data: pieData,
        },
      ],
    };
  }

  // ---- 各图表加载逻辑 ----

  async function loadPlanTrend() {
    const key = "plan-trend";
    const category = document.querySelector("[data-plan-category]").value;
    const majorSelect = document.querySelector("[data-plan-major]");
    const majorOption = majorSelect.options[majorSelect.selectedIndex];
    const majorCode = majorSelect.value;
    const majorName = majorOption ? majorOption.dataset.majorName || "" : "";
    try {
      const payload = await App.fetchJson(
        `/api/chart/plan-trend${App.buildQuery({
          major_category: category,
          major_code: majorCode,
          major_name: majorName,
        })}`
      );
      if (isEmpty(payload)) return showEmpty(key, payload);
      getChart(key).setOption(dualAxisLineOption(payload), true);
      setNote(key, payload);
    } catch (error) {
      showEmpty(key, { warnings: [error.message] });
    }
  }

  async function loadMajorHeat() {
    const key = "major-heat";
    const year = document.querySelector("[data-heat-year]").value;
    try {
      const payload = await App.fetchJson(
        `/api/chart/major-heat${App.buildQuery({ year, top: 10 })}`
      );
      if (isEmpty(payload)) return showEmpty(key, payload);
      getChart(key).setOption(dualAxisBarOption(payload, true), true);
      setNote(key, payload);
    } catch (error) {
      showEmpty(key, { warnings: [error.message] });
    }
  }

  async function loadUniversityType() {
    const key = "university-type";
    const dimension = document.querySelector("[data-type-dimension]").value;
    try {
      const payload = await App.fetchJson(
        `/api/chart/university-type${App.buildQuery({ dimension })}`
      );
      if (isEmpty(payload)) return showEmpty(key, payload);
      getChart(key).setOption(pieOption(payload), true);
      setNote(key, payload);
    } catch (error) {
      showEmpty(key, { warnings: [error.message] });
    }
  }

  async function loadLineTrend() {
    const key = "line-trend";
    const universityId = document.querySelector("[data-line-university]").value;
    const majorSelect = document.querySelector("[data-line-major]");
    const scoreLineMajorName = majorSelect.value;
    if (!universityId || !scoreLineMajorName) {
      return showEmpty(key, { warnings: ["请选择学校和专业以查看复试线趋势。"] });
    }
    try {
      const payload = await App.fetchJson(
        `/api/chart/line-trend${App.buildQuery({
          university_id: universityId,
          score_line_major_name: scoreLineMajorName,
        })}`
      );
      if (isEmpty(payload)) return showEmpty(key, payload);
      getChart(key).setOption(baseLineOption(payload), true);
      setNote(key, payload);
    } catch (error) {
      showEmpty(key, { warnings: [error.message] });
    }
  }

  // ---- 下拉数据初始化 ----

  async function initPlanCategorySelect() {
    const select = document.querySelector("[data-plan-category]");
    try {
      const data = await App.fetchJson("/api/metadata/major-categories");
      const list = (data && data.from_majors) || [];
      list.forEach((name) => {
        const opt = document.createElement("option");
        opt.value = name;
        opt.textContent = name;
        select.appendChild(opt);
      });
    } catch (error) {
      App.showToast(error.message);
    }
  }

  async function loadPlanMajorOptions(category) {
    const select = document.querySelector("[data-plan-major]");
    select.innerHTML = '<option value="">加载专业中...</option>';
    try {
      const data = await App.fetchJson(
        `/api/metadata/plan-majors${App.buildQuery({ major_category: category, limit: 1000 })}`
      );
      const items = (data && data.items) || [];
      select.innerHTML =
        '<option value="">全部专业</option>' +
        items
          .map((item) => {
            const code = item.major_code || "";
            const name = item.major_name || "";
            const categoryText = item.major_category ? ` · ${item.major_category}` : "";
            const label = `${code} ${name}${categoryText}`.trim();
            return (
              `<option value="${App.escapeHtml(code)}" data-major-name="${App.escapeHtml(name)}">` +
              `${App.escapeHtml(label)}</option>`
            );
          })
          .join("");
    } catch (error) {
      select.innerHTML = '<option value="">专业加载失败</option>';
      App.showToast(error.message);
    }
  }

  async function initYearSelect() {
    const select = document.querySelector("[data-heat-year]");
    try {
      const detail = await App.fetchJson("/api/health");
      const info = detail.detail || {};
      const min = Number(info.min_year) || 2024;
      const max = Number(info.max_year) || 2026;
      const years = [];
      for (let y = max; y >= min; y -= 1) years.push(y);
      select.innerHTML = years
        .map((y, idx) => `<option value="${App.escapeHtml(y)}"${idx === 0 ? " selected" : ""}>${App.escapeHtml(y)} 年</option>`)
        .join("");
    } catch (error) {
      select.innerHTML = '<option value="2026" selected>2026 年</option>';
    }
  }

  async function initUniversitySelect() {
    const select = document.querySelector("[data-line-university]");
    try {
      const data = await App.fetchJson("/api/university/list?limit=200");
      const items = data.items || [];
      select.innerHTML =
        '<option value="">请选择学校</option>' +
        items
          .map((u) => `<option value="${App.escapeHtml(u.id)}">${App.escapeHtml(u.university_name)}</option>`)
          .join("");
    } catch (error) {
      select.innerHTML = '<option value="">学校加载失败</option>';
    }
  }

  async function loadMajorsForUniversity(universityId) {
    const select = document.querySelector("[data-line-major]");
    select.innerHTML = '<option value="">加载专业中...</option>';
    if (!universityId) {
      select.innerHTML = '<option value="">请先选择学校</option>';
      return;
    }
    try {
      const data = await App.fetchJson(
        `/api/metadata/score-line-majors${App.buildQuery({ university_id: universityId, limit: 1000 })}`
      );
      const items = data.items || [];
      if (!items.length) {
        select.innerHTML = '<option value="">该校暂无复试线专业数据</option>';
        return;
      }
      select.innerHTML =
        '<option value="">请选择专业</option>' +
        items
          .map((m) => {
            const name = m.score_line_major_name || "";
            return `<option value="${App.escapeHtml(name)}">${App.escapeHtml(name)}</option>`;
          })
          .join("");
    } catch (error) {
      select.innerHTML = '<option value="">专业加载失败</option>';
    }
  }

  // ---- 事件绑定 ----

  function bindEvents() {
    document.querySelector("[data-plan-category]").addEventListener("change", async (event) => {
      await loadPlanMajorOptions(event.target.value);
      loadPlanTrend();
    });
    document.querySelector("[data-plan-major]").addEventListener("change", loadPlanTrend);
    document.querySelector("[data-heat-year]").addEventListener("change", loadMajorHeat);
    document.querySelector("[data-type-dimension]").addEventListener("change", loadUniversityType);
    document.querySelector("[data-line-university]").addEventListener("change", async (e) => {
      await loadMajorsForUniversity(e.target.value);
      loadLineTrend();
    });
    document.querySelector("[data-line-major]").addEventListener("change", loadLineTrend);
    window.addEventListener("resize", () => {
      Object.values(charts).forEach((chart) => chart.resize());
    });
  }

  async function init() {
    bindEvents();
    await Promise.all([initPlanCategorySelect(), initYearSelect(), initUniversitySelect()]);
    await loadPlanMajorOptions(document.querySelector("[data-plan-category]").value);
    await Promise.all([loadPlanTrend(), loadMajorHeat(), loadUniversityType()]);
    showEmpty("line-trend", { warnings: ["请选择学校和专业以查看复试线趋势。"] });
  }

  document.addEventListener("DOMContentLoaded", init);
})();
