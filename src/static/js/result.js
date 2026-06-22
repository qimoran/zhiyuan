(function () {
  const scoreSummary = document.querySelector("[data-score-summary]");
  const statsSummary = document.querySelector("[data-stats-summary]");
  const columns = document.querySelector("[data-result-columns]");
  const globalWarning = document.querySelector("[data-global-warning]");
  const generateReportButton = document.querySelector("[data-generate-report]");
  const saveResultButton = document.querySelector("[data-save-result]");

  if (!scoreSummary || !statsSummary || !columns) return;

  const state = {
    selected: null,
  };

  const tierConfigs = [
    { key: "rush", title: "冲刺档", cls: "rush", icon: "◎", empty: "冲刺档暂无推荐" },
    { key: "stable", title: "稳妥档", cls: "stable", icon: "盾", empty: "稳妥档暂无推荐" },
    { key: "safe", title: "保底档", cls: "safe", icon: "↗", empty: "保底档暂无推荐" },
  ];

  function setActionsEnabled(enabled) {
    if (generateReportButton) generateReportButton.disabled = !enabled;
    if (saveResultButton) saveResultButton.disabled = !enabled;
  }

  function clearResultArea() {
    statsSummary.innerHTML = "";
    columns.innerHTML = "";
    if (globalWarning) globalWarning.hidden = true;
  }

  function renderLoginRequired() {
    scoreSummary.innerHTML = `
      <div class="score-empty">
        <h1>请先登录</h1>
        <p class="muted">推荐结果页面需要登录后查看，登录后完成推荐会自动保存到个人历史记录。</p>
        <a class="btn btn-primary" href="/login?next=/result">登录</a>
      </div>
    `;
    clearResultArea();
    setActionsEnabled(false);
  }

  function renderLoading(text) {
    scoreSummary.innerHTML = `
      <div class="score-empty">
        <h1>${App.escapeHtml(text)}</h1>
        <p class="muted">请稍候。</p>
      </div>
    `;
    clearResultArea();
    setActionsEnabled(false);
  }

  function renderEmptyHistory() {
    scoreSummary.innerHTML = `
      <div class="score-empty">
        <h1>暂无推荐结果</h1>
        <p class="muted">请先完成推荐表单，历史推荐记录可在个人中心查看。</p>
        <a class="btn btn-primary" href="/recommend">开始推荐</a>
      </div>
    `;
    clearResultArea();
    setActionsEnabled(false);
  }

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

  function normalizeDetail(detail) {
    const request = detail.request || {};
    const storedResult = detail.result || {};
    const summary = storedResult.summary || {};
    const result = {
      ...storedResult,
      recommendation_log_id: detail.id,
      trace_id: detail.trace_id,
      warnings: detail.warnings || storedResult.warnings || [],
      candidate_count: storedResult.candidate_count ?? summary.candidate_count ?? 0,
      returned_count: storedResult.returned_count ?? summary.returned_count ?? 0,
    };
    return { detail, request, result };
  }

  function recommendationGroups(result) {
    return result.recommendations || {
      rush: result.rush || [],
      stable: result.stable || [],
      safe: result.safe || [],
    };
  }

  function renderInlineMarkdown(value) {
    return App.escapeHtml(value || "")
      .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
      .replace(/\[([^\]]+)\]\((https?:\/\/[^)\s]+)\)/g, '<a href="$2" target="_blank" rel="noopener noreferrer">$1</a>');
  }

  function renderMarkdown(markdownText) {
    return String(markdownText || "")
      .split("\n")
      .map((line) => {
        const trimmed = line.trimStart();
        if (!trimmed) return "";
        if (trimmed.startsWith("#### ")) return `<h5>${renderInlineMarkdown(trimmed.slice(5))}</h5>`;
        if (trimmed.startsWith("### ")) return `<h4>${renderInlineMarkdown(trimmed.slice(4))}</h4>`;
        if (trimmed.startsWith("## ")) return `<h4>${renderInlineMarkdown(trimmed.slice(3))}</h4>`;
        if (trimmed.startsWith("# ")) return `<h4>${renderInlineMarkdown(trimmed.slice(2))}</h4>`;
        if (trimmed.startsWith("- ")) return `<p class="markdown-bullet">${renderInlineMarkdown(trimmed.slice(2))}</p>`;
        if (/^\d+\.\s/.test(trimmed)) return `<p class="markdown-number">${renderInlineMarkdown(trimmed)}</p>`;
        return `<p>${renderInlineMarkdown(trimmed)}</p>`;
      })
      .join("");
  }

  function buildClientMarkdown(item, request) {
    const warnings = item.warnings && item.warnings.length ? item.warnings : ["暂无额外风险提示，但仍需核对当年官网公告。"];
    return `
### 推荐结论
- ${item.university_name || "该院校"} ${item.major_name || request.major_name || "目标专业"} 可作为${rankLabel(item.rank_type)}参考。
- ${item.reason || "系统根据分数线、招生计划和数据质量综合生成。"}

### 分数匹配
- 用户总分：${request.total_score || "未填写"} 分；当前参考复试线：${item.score_line || "暂无"} 分。
- 总分分差：${formatDiff(item.score_diff)}。

### 招生与趋势
- 当前招生计划：${item.plan_count ?? "暂无"} 人。
- 近年招生计划：${formatHistory(item.plan_history, "plan_count", "人")}
- 近年复试线：${formatHistory(item.score_line_history, "total_score_line", "分")}

### 资料核验
- ${item.evidence_summary || "当前没有匹配到明确的资料核验证据，建议以学校官网最新公告为准。"}

### 风险提示
${warnings.map((warning) => `- ${warning}`).join("\n")}
    `.trim();
  }

  function renderRecommendationMarkdown(item, request) {
    const markdown = item.recommendation_markdown || buildClientMarkdown(item, request);
    const source = item.recommendation_markdown_source === "llm" ? "AI整理" : "模板整理";
    return `
      <div class="recommendation-markdown-card" role="button" tabindex="0" aria-expanded="false">
        <div class="recommendation-markdown-head">
          <strong>推荐分析</strong>
          <span>${App.escapeHtml(source)}</span>
        </div>
        <div class="recommendation-markdown-body">${renderMarkdown(markdown)}</div>
      </div>
    `;
  }

  function rankLabel(value) {
    return { rush: "冲刺", stable: "稳妥", safe: "保底" }[value] || "推荐";
  }

  function formatDiff(value) {
    const number = Number(value);
    if (!Number.isFinite(number)) return "暂无";
    return `${number >= 0 ? "+" : ""}${number} 分`;
  }

  function formatHistory(items, field, unit) {
    if (!Array.isArray(items) || !items.length) return "暂无记录。";
    return `${items.map((item) => `${item.year}年 ${item[field] ?? "暂无"}${unit}`).join("，")}。`;
  }

  function renderCard(item, tierKey, request, totalScore) {
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
        ${renderRecommendationMarkdown(item, request)}
      </article>
    `;
  }

  function renderDetail(detail) {
    const normalized = normalizeDetail(detail);
    state.selected = normalized;
    const { request, result } = normalized;
    const groups = recommendationGroups(result);
    const totalScore = asNumber(request.total_score, 0);
    const returnedCount =
      result.returned_count ?? result.return_count ?? Object.values(groups).reduce((sum, list) => sum + (list || []).length, 0);

    sessionStorage.setItem("recommendationRequest", JSON.stringify(request));
    sessionStorage.setItem("recommendationResult", JSON.stringify(result));

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
      <span>共找到 <strong>${App.escapeHtml(result.candidate_count ?? 0)}</strong> 个候选学校，返回 <strong>${App.escapeHtml(returnedCount)}</strong> 个推荐</span>
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

    columns.innerHTML = tierConfigs
      .map((config) => {
        const items = groups[config.key] || [];
        const content = items.length
          ? items.map((item) => renderCard(item, config.key, request, totalScore)).join("")
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
    setActionsEnabled(true);
  }

  async function selectHistory(logId) {
    setActionsEnabled(false);
    try {
      const detail = await App.fetchJson(`/api/me/recommendations/${logId}`);
      renderDetail(detail);
    } catch (error) {
      App.showToast(error.message || "读取推荐结果失败。");
      setActionsEnabled(false);
    }
  }

  function latestSessionLogId() {
    const result = JSON.parse(sessionStorage.getItem("recommendationResult") || "null");
    return result && result.recommendation_log_id ? String(result.recommendation_log_id) : "";
  }

  async function loadUserResults() {
    renderLoading("正在读取推荐结果");
    try {
      const data = await App.fetchJson("/api/me/recommendations");
      const items = data.items || [];
      if (!items.length) {
        renderEmptyHistory();
        return;
      }
      const sessionLogId = latestSessionLogId();
      const selected = items.find((item) => String(item.id) === sessionLogId) || items[0];
      await selectHistory(selected.id);
    } catch (error) {
      scoreSummary.innerHTML = `
        <div class="score-empty">
          <h1>读取推荐结果失败</h1>
          <p class="muted">${App.escapeHtml(error.message || "请稍后重试。")}</p>
        </div>
      `;
      clearResultArea();
      setActionsEnabled(false);
    }
  }

  columns.addEventListener("click", (event) => {
    if (event.target.closest(".recommendation-markdown-card a")) return;
    const markdownCard = event.target.closest(".recommendation-markdown-card");
    if (!markdownCard) return;
    const expanded = !markdownCard.classList.contains("expanded");
    markdownCard.classList.toggle("expanded", expanded);
    markdownCard.setAttribute("aria-expanded", expanded ? "true" : "false");
  });

  columns.addEventListener("keydown", (event) => {
    if (event.key !== "Enter" && event.key !== " ") return;
    const markdownCard = event.target.closest(".recommendation-markdown-card");
    if (!markdownCard) return;
    event.preventDefault();
    const expanded = !markdownCard.classList.contains("expanded");
    markdownCard.classList.toggle("expanded", expanded);
    markdownCard.setAttribute("aria-expanded", expanded ? "true" : "false");
  });

  if (saveResultButton) {
    saveResultButton.addEventListener("click", () => {
      if (!state.selected) {
        App.showToast("请先选择一条推荐记录。");
        return;
      }
      localStorage.setItem(
        "savedRecommendationResult",
        JSON.stringify({
          request: state.selected.request,
          result: state.selected.result,
          saved_at: new Date().toISOString(),
        })
      );
      App.showToast("推荐结果已保存到本地浏览器。");
    });
  }

  if (generateReportButton) {
    generateReportButton.addEventListener("click", () => {
      if (!state.selected) {
        App.showToast("请先选择一条推荐记录。");
        return;
      }
      window.location.href = "/report";
    });
  }

  if (!App.auth.loaded) {
    renderLoading("正在验证登录状态");
    document.addEventListener(
      "app:auth-ready",
      (event) => {
        if (!event.detail.authenticated) {
          renderLoginRequired();
          return;
        }
        loadUserResults();
      },
      { once: true }
    );
    return;
  }

  if (!App.auth.authenticated) {
    renderLoginRequired();
    return;
  }
  loadUserResults();
})();
