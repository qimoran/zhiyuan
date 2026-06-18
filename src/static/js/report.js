(function () {
  const target = document.querySelector("[data-report-summary]");
  if (!target) return;
  const result = JSON.parse(sessionStorage.getItem("recommendationResult") || "null");
  const request = JSON.parse(sessionStorage.getItem("recommendationRequest") || "null");
  if (!result || !request) {
    target.innerHTML = `
      <h2>暂无推荐摘要</h2>
      <p class="muted">请先完成一次推荐，再生成报告。</p>
      <a class="btn btn-primary" href="/recommend">开始推荐</a>
    `;
    return;
  }
  const recs = result.recommendations || {};
  target.innerHTML = `
    <h2>最近一次推荐摘要</h2>
    <ul class="report-list">
      <li>目标年份：${App.escapeHtml(request.target_year)}</li>
      <li>目标专业：${App.escapeHtml(request.major_name)} / ${App.escapeHtml(request.major_category)}</li>
      <li>成绩：总分 ${App.escapeHtml(request.total_score)}，政治 ${App.escapeHtml(request.politics_score)}，英语 ${App.escapeHtml(request.english_score)}</li>
      <li>返回结果：冲刺 ${(recs.rush || []).length} 个，稳妥 ${(recs.stable || []).length} 个，保底 ${(recs.safe || []).length} 个</li>
    </ul>
  `;
})();
