(function () {
  const summaryTarget = document.querySelector("[data-report-summary]");
  const content = document.querySelector("[data-report-content]");
  const status = document.querySelector("[data-report-status]");
  const generateButton = document.querySelector("[data-report-generate]");
  const saveButton = document.querySelector("[data-report-save]");
  if (!summaryTarget || !content || !status || !generateButton || !saveButton) return;

  const state = {
    selected: null,
    latestReport: null,
  };

  function renderReport(markdownText) {
    const lines = String(markdownText || "").split("\n");
    const html = [];
    for (let index = 0; index < lines.length; index += 1) {
      const line = lines[index];
      const trimmed = line.trimStart();
      if (isTableStart(lines, index)) {
        const tableLines = [];
        while (index < lines.length && lines[index].trim().startsWith("|")) {
          tableLines.push(lines[index]);
          index += 1;
        }
        index -= 1;
        html.push(renderMarkdownTable(tableLines));
        continue;
      }
      if (trimmed.startsWith("# ")) html.push(`<h2>${renderInlineMarkdown(trimmed.slice(2))}</h2>`);
      else if (trimmed.startsWith("## ")) html.push(`<h3>${renderInlineMarkdown(trimmed.slice(3))}</h3>`);
      else if (trimmed.startsWith("### ")) html.push(`<h4>${renderInlineMarkdown(trimmed.slice(4))}</h4>`);
      else if (trimmed.startsWith("> ")) html.push(`<blockquote>${renderInlineMarkdown(trimmed.slice(2))}</blockquote>`);
      else if (trimmed.startsWith("- ")) html.push(`<p class="report-bullet">${renderInlineMarkdown(trimmed.slice(2))}</p>`);
      else if (/^\d+\.\s/.test(trimmed)) html.push(`<p class="report-number">${renderInlineMarkdown(trimmed)}</p>`);
      else if (line.trim() === "") html.push("");
      else html.push(`<p>${renderInlineMarkdown(line)}</p>`);
    }
    return html.join("");
  }

  function renderInlineMarkdown(value) {
    return App.escapeHtml(value || "")
      .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
      .replace(/\[([^\]]+)\]\((https?:\/\/[^)\s]+)\)/g, '<a href="$2" target="_blank" rel="noopener noreferrer">$1</a>');
  }

  function isTableStart(lines, index) {
    const current = lines[index]?.trim() || "";
    const next = lines[index + 1]?.trim() || "";
    return current.startsWith("|") && next.startsWith("|") && /^\|?[\s:-|]+\|?$/.test(next);
  }

  function parseTableCells(line) {
    return line
      .trim()
      .replace(/^\|/, "")
      .replace(/\|$/, "")
      .split("|")
      .map((cell) => cell.trim());
  }

  function renderMarkdownTable(tableLines) {
    const headers = parseTableCells(tableLines[0] || "");
    const rows = tableLines.slice(2).map(parseTableCells);
    return `
      <div class="report-table-wrap">
        <table class="report-markdown-table">
          <thead>
            <tr>${headers.map((cell) => `<th>${renderInlineMarkdown(cell)}</th>`).join("")}</tr>
          </thead>
          <tbody>
            ${rows
              .map(
                (row) => `
                  <tr>${headers.map((_, index) => `<td>${renderInlineMarkdown(row[index] || "")}</td>`).join("")}</tr>
                `
              )
              .join("")}
          </tbody>
        </table>
      </div>
    `;
  }

  function buildStatusText(report) {
    if (!report) return "请选择一条历史推荐记录后生成报告。";
    if (report.report_type === "llm") {
      const model = report.llm_model ? `，模型：${report.llm_model}` : "";
      return `AI 推荐报告已生成并入库，report_id=${report.report_id}${model}。`;
    }
    if (report.ai_status === "fallback") {
      const reason = report.fallback_reason ? `原因：${report.fallback_reason}` : "大模型接口暂不可用。";
      return `已生成模板降级报告，report_id=${report.report_id}。${reason}`;
    }
    return `推荐报告已生成并入库，report_id=${report.report_id}。`;
  }

  function renderLoggedOut() {
    summaryTarget.innerHTML = `
      <h2>请登录后查看个人推荐历史</h2>
      <p class="muted">推荐报告页会根据当前登录用户展示历史推荐摘要，并支持点开生成报告。</p>
      <a class="btn btn-primary" href="/login?next=/report">登录</a>
    `;
    content.innerHTML = "";
    status.textContent = "未登录时不会展示个人历史推荐记录。";
    generateButton.disabled = true;
    saveButton.disabled = true;
  }

  function renderEmptyHistory() {
    summaryTarget.innerHTML = `
      <h2>暂无推荐历史</h2>
      <p class="muted">登录后完成一次智能推荐，这里会显示对应的推荐摘要。</p>
      <a class="btn btn-primary" href="/recommend">开始推荐</a>
    `;
    content.innerHTML = "";
    status.textContent = "暂无可生成报告的历史推荐。";
    generateButton.disabled = true;
    saveButton.disabled = true;
  }

  function renderHistory(items) {
    summaryTarget.innerHTML = `
      <h2>我的历史推荐</h2>
      <div class="history-list report-history-list">
        ${items
          .map(
            (item) => `
              <button class="history-item" type="button" data-history-id="${item.id}">
                <span>
                  <strong>${App.escapeHtml(item.major_name || "未填写专业")}</strong>
                  <small>${App.escapeHtml(item.created_at || "")} · ${App.escapeHtml(item.target_year || "")}年 · 总分 ${App.escapeHtml(item.total_score || "未填")}</small>
                </span>
                <em>冲刺 ${App.escapeHtml(item.rush || 0)} / 稳妥 ${App.escapeHtml(item.stable || 0)} / 保底 ${App.escapeHtml(item.safe || 0)}</em>
              </button>
            `
          )
          .join("")}
      </div>
    `;
  }

  function renderSelectedDetail(detail) {
    const result = detail.result || {};
    const recommendations = result.recommendations || {};
    const summary = result.summary || {};
    const request = detail.request || {};
    const counts = {
      rush: (recommendations.rush || []).length || summary.rush || 0,
      stable: (recommendations.stable || []).length || summary.stable || 0,
      safe: (recommendations.safe || []).length || summary.safe || 0,
    };
    status.textContent = "已选择历史推荐记录，可生成 AI 推荐报告。";
    generateButton.disabled = false;
    saveButton.disabled = true;
    state.latestReport = null;
    content.innerHTML = renderReport(buildSelectedDetailMarkdown(detail, recommendations, counts));
  }

  function buildSelectedDetailMarkdown(detail, recommendations, counts) {
    const request = detail.request || {};
    return [
      "# 推荐摘要",
      "",
      `- 推荐时间：${markdownText(detail.created_at || "暂无")}`,
      `- 目标年份：${markdownText(request.target_year || detail.target_year || "暂无")}`,
      `- 目标专业：${markdownText(request.major_name || request.major_category || detail.major_name || "未填写")}`,
      `- 成绩：总分 ${markdownText(request.total_score || detail.total_score || "未填写")}`,
      `- 返回结果：冲刺 ${counts.rush} 个，稳妥 ${counts.stable} 个，保底 ${counts.safe} 个`,
      "",
      "## 推荐结果预览",
      "",
      renderRecommendationPreviewMarkdown(recommendations),
    ].join("\n");
  }

  function renderRecommendationPreviewMarkdown(recommendations) {
    const labels = { rush: "冲刺档", stable: "稳妥档", safe: "保底档" };
    return ["rush", "stable", "safe"]
      .map((key) => {
        const items = recommendations[key] || [];
        if (!items.length) {
          return [`### ${labels[key]}`, "", "- 暂无推荐"].join("\n");
        }
        const rows = items.slice(0, 5).map((item) =>
          [
            markdownCell(item.university_name || "未知学校"),
            markdownCell(item.major_name || "暂无"),
            markdownCell(item.score_line ?? "暂无"),
            markdownCell(formatDiff(item.score_diff)),
          ].join(" | ")
        );
        return [
          `### ${labels[key]}`,
          "",
          "| 学校 | 专业 | 复试线 | 分差 |",
          "| --- | --- | --- | --- |",
          ...rows.map((row) => `| ${row} |`),
        ].join("\n");
      })
      .join("\n\n");
  }

  function markdownText(value) {
    return String(value ?? "").replace(/\|/g, "/").trim();
  }

  function markdownCell(value) {
    return markdownText(value) || "暂无";
  }

  function formatDiff(value) {
    if (value === null || value === undefined || value === "") return "暂无";
    const number = Number(value);
    if (!Number.isFinite(number)) return value;
    return `${number >= 0 ? "+" : ""}${number} 分`;
  }

  async function selectHistory(logId) {
    status.textContent = "正在读取历史推荐详情...";
    generateButton.disabled = true;
    try {
      const detail = await App.fetchJson(`/api/me/recommendations/${logId}`);
      state.selected = detail;
      summaryTarget.querySelectorAll(".history-item").forEach((item) => {
        item.classList.toggle("active", item.dataset.historyId === String(logId));
      });
      renderSelectedDetail(detail);
    } catch (error) {
      status.textContent = error.message || "读取历史推荐详情失败。";
    }
  }

  async function loadHistory() {
    status.textContent = "正在读取个人推荐历史...";
    try {
      const data = await App.fetchJson("/api/me/recommendations");
      const items = data.items || [];
      if (!items.length) {
        renderEmptyHistory();
        return;
      }
      renderHistory(items);
      await selectHistory(items[0].id);
    } catch (error) {
      status.textContent = error.message || "读取个人推荐历史失败。";
      generateButton.disabled = true;
      saveButton.disabled = true;
    }
  }

  function applyReport(report) {
    state.latestReport = report;
    content.innerHTML = renderReport(report.report_content);
    status.textContent = buildStatusText(report);
    saveButton.disabled = false;
  }

  async function generateReport() {
    if (!state.selected) {
      App.showToast("请先选择一条历史推荐。");
      return;
    }
    generateButton.disabled = true;
    generateButton.textContent = "正在生成...";
    status.textContent = "正在调用 AI 接口生成推荐报告。";
    try {
      const result = {
        ...(state.selected.result || {}),
        warnings: state.selected.warnings || [],
      };
      const report = await App.fetchJson("/api/report/generate", {
        method: "POST",
        body: JSON.stringify({
          report_type: "llm",
          recommendation_log_id: state.selected.id,
          recommendation_trace_id: state.selected.trace_id,
          request: state.selected.request || {},
          recommendation_result: result,
        }),
      });
      applyReport(report);
      App.showToast("推荐报告已生成。");
    } catch (error) {
      status.textContent = error.message || "报告生成失败，请稍后重试。";
    } finally {
      generateButton.disabled = false;
      generateButton.textContent = "重新生成 AI 报告";
    }
  }

  summaryTarget.addEventListener("click", (event) => {
    const button = event.target.closest("[data-history-id]");
    if (!button) return;
    selectHistory(button.dataset.historyId);
  });

  generateButton.addEventListener("click", generateReport);
  saveButton.addEventListener("click", () => {
    if (!state.latestReport) {
      App.showToast("请先生成报告。");
      return;
    }
    localStorage.setItem("savedRecommendationReport", JSON.stringify(state.latestReport));
    App.showToast("报告已保存到本地浏览器。");
  });

  generateButton.disabled = true;
  saveButton.disabled = true;
  document.addEventListener("app:auth-ready", (event) => {
    if (!event.detail.authenticated) {
      renderLoggedOut();
      return;
    }
    loadHistory();
  });
  if (App.auth.loaded) {
    if (App.auth.authenticated) {
      loadHistory();
    } else {
      renderLoggedOut();
    }
  }
})();
