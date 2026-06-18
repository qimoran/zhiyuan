(function () {
  const result = JSON.parse(sessionStorage.getItem("recommendationResult") || "null");
  const request = JSON.parse(sessionStorage.getItem("recommendationRequest") || "null");
  const scoreSummary = document.querySelector("[data-score-summary]");
  const statsSummary = document.querySelector("[data-stats-summary]");
  const columns = document.querySelector("[data-result-columns]");
  const globalWarning = document.querySelector("[data-global-warning]");

  if (!scoreSummary || !statsSummary || !columns) return;

  if (!result || !request) {
    scoreSummary.innerHTML = `
      <div class="score-empty">
        <h1>暂无推荐结果</h1>
        <p class="muted">请先完成推荐表单。</p>
        <a class="btn btn-primary" href="/recommend">开始推荐</a>
      </div>
    `;
    statsSummary.innerHTML = "";
    columns.innerHTML = "";
    return;
  }

  const tierConfigs = [
    { key: "rush", title: "冲刺档", cls: "rush", icon: "◎", empty: "冲刺档暂无推荐" },
    { key: "stable", title: "稳妥档", cls: "stable", icon: "盾", empty: "稳妥档暂无推荐" },
    { key: "safe", title: "保底档", cls: "safe", icon: "↗", empty: "保底档暂无推荐" },
  ];

  function asNumber(value, fallback) {
    const number = Number(value);
    return Number.isFinite(number) ? number : fallback;
  }

  function scoreMax(label) {
    return label.includes("专业课") ? 150 : 100;
  }

  function renderScoreBar(label, value) {
    const score = asNumber(value, 0);
    const pct = Math.max(0, Math.min(100, Math.round((score / scoreMax(label)) * 100)));
    return `
      <div class="result-score-item">
        <div class="result-score-line">
          <span>${App.escapeHtml(label)}</span>
          <strong>${App.escapeHtml(score)}</strong>
        </div>
        <div class="result-score-track"><span style="width: ${pct}%"></span></div>
      </div>
    `;
  }

  function levelLabel(value) {
    const text = String(value || "").replaceAll(" ", "");
    if (text.includes("985")) return "985/211";
    if (text.includes("211")) return "211";
    if (text.includes("双一流")) return "双一流";
    if (text.includes("普通")) return "普通院校";
    return value || "层次待补充";
  }

  function levelClass(value) {
    const label = levelLabel(value);
    if (label === "985/211") return "school-level school-level-elite";
    if (label === "211") return "school-level school-level-strong";
    if (label === "双一流") return "school-level school-level-first-class";
    return "school-level school-level-normal";
  }

  function starCount(item, tierKey) {
    if (item.stars) return Math.max(1, Math.min(5, Number(item.stars)));
    const diff = asNumber(item.score_diff, 0);
    if (tierKey === "safe") return 5;
    if (tierKey === "stable") return diff >= 10 ? 5 : 4;
    if (diff >= 0) return 4;
    return 3;
  }

  function renderStars(item, tierKey) {
    const count = starCount(item, tierKey);
    return Array.from({ length: 5 })
      .map((_, index) => `<span class="${index < count ? "filled" : ""}">★</span>`)
      .join("");
  }

  function recommendationGroups() {
    return result.recommendations || {
      rush: result.rush || [],
      stable: result.stable || [],
      safe: result.safe || [],
    };
  }

  const groups = recommendationGroups();
  const totalScore = asNumber(request.total_score, 0);
  const returnedCount = result.returned_count ?? result.return_count ?? Object.values(groups).reduce((sum, list) => sum + (list || []).length, 0);

  scoreSummary.innerHTML = `
    <div class="result-total-box">
      <span>考研总分</span>
      <strong>${App.escapeHtml(totalScore)}</strong>
      <small>满分 400</small>
    </div>
    <div class="result-score-grid">
      ${renderScoreBar("政治", request.politics_score)}
      ${renderScoreBar("英语", request.english_score)}
      ${renderScoreBar("专业课一", request.subject_one_score)}
      ${renderScoreBar("专业课二", request.subject_two_score)}
    </div>
  `;

  statsSummary.innerHTML = `
    <span>共找到 <strong>${App.escapeHtml(result.candidate_count ?? 0)}</strong> 个候选学校， 返回 <strong>${App.escapeHtml(returnedCount)}</strong> 个推荐</span>
    <span class="dot"></span>
    <span>专业：<strong>${App.escapeHtml(request.major_name || request.major_category || "未填写")}</strong></span>
    <span class="dot"></span>
    <span>${App.escapeHtml(request.target_year || "2026")}年</span>
  `;

  if (result.warnings && result.warnings.length) {
    globalWarning.hidden = false;
    globalWarning.innerHTML = result.warnings.map((item) => App.escapeHtml(item)).join("<br>");
  } else {
    globalWarning.hidden = true;
  }

  function renderWarning(item, diff) {
    const warnings = item.warnings && item.warnings.length ? item.warnings : [];
    const warning = warnings[0] || (diff < 0 ? `总分低于近三年录取均线${Math.abs(diff)}分，建议重点备考` : "");
    if (!warning) return "";
    return `<div class="result-card-warning"><span>△</span>${App.escapeHtml(warning)}</div>`;
  }

  function renderCard(item, tierKey) {
    const diff = asNumber(item.score_diff, totalScore - asNumber(item.score_line, totalScore));
    const scoreLine = asNumber(item.score_line, 0);
    const pct = Math.max(8, Math.min(100, Math.round((totalScore / Math.max(totalScore, scoreLine, 1)) * 100)));
    const diffText = `${diff >= 0 ? "+" : ""}${diff} 分`;
    const studyMode = App.labelStudyMode(item.study_mode) || "学习方式待补充";
    const degreeType = App.labelDegree(item.degree_type) || "学位待补充";
    const level = levelLabel(item.school_level || item.university_level);
    return `
      <article class="recommend-card ${tierKey}">
        <div class="result-card-head">
          <div>
            <h3>${App.escapeHtml(item.university_name)}</h3>
            <span class="${levelClass(level)}">${App.escapeHtml(level)}</span>
          </div>
          <div class="result-stars" aria-label="推荐星级">${renderStars(item, tierKey)}</div>
        </div>
        <p class="result-major-line">
          ${App.escapeHtml(item.major_name || request.major_name || "目标专业")}
          <span>·</span>
          <em>${App.escapeHtml(degreeType)}</em>
          <span>·</span>
          <em>${App.escapeHtml(studyMode)}</em>
        </p>
        <div class="result-score-compare">
          <span>录取线 <strong>${App.escapeHtml(scoreLine || "待补充")}</strong></span>
          <b class="${diff >= 0 ? "positive" : "negative"}">${App.escapeHtml(diffText)}</b>
          <span>你的分数 <strong>${App.escapeHtml(totalScore)}</strong></span>
        </div>
        <div class="result-match-track"><span style="width: ${pct}%"></span></div>
        ${renderWarning(item, diff)}
        <button class="reason-box" type="button">
          推荐理由 <span class="reason-arrow">⌄</span>
          <span class="reason-detail">${App.escapeHtml(item.reason || "暂无推荐理由")}</span>
        </button>
      </article>
    `;
  }

  columns.innerHTML = tierConfigs
    .map((config) => {
      const items = groups[config.key] || [];
      const content = items.length
        ? items.map((item) => renderCard(item, config.key)).join("")
        : `<div class="empty-state">${config.empty}</div>`;
      return `
        <section class="recommend-column ${config.cls}">
          <div class="column-title">
            <span><i>${config.icon}</i>${config.title}</span>
            <strong>${items.length} 所</strong>
          </div>
          <div class="column-body">${content}</div>
        </section>
      `;
    })
    .join("");

  columns.addEventListener("click", (event) => {
    const reason = event.target.closest(".reason-box");
    if (reason) reason.classList.toggle("expanded");
  });

  document.querySelector("[data-save-result]").addEventListener("click", () => {
    localStorage.setItem("savedRecommendationResult", JSON.stringify({ request, result, saved_at: new Date().toISOString() }));
    App.showToast("推荐结果已保存到本地浏览器。");
  });

  document.querySelector("[data-generate-report]").addEventListener("click", () => {
    window.location.href = "/report";
  });
})();
