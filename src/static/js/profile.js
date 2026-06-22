(function () {
  const summary = document.querySelector("[data-profile-summary]");
  const form = document.querySelector("[data-profile-form]");
  if (!summary || !form) return;
  const historyBox = document.querySelector("[data-profile-history]");
  const metricsBox = document.querySelector("[data-profile-metrics]");
  const errorBox = document.querySelector("[data-profile-error]");
  const submitButton = form.querySelector("button[type='submit']");

  function renderLoggedOut() {
    summary.innerHTML = `
      <div class="profile-account-banner">
        <div class="profile-avatar muted-avatar">未</div>
        <div class="profile-account-main">
          <span class="profile-status-pill">未登录</span>
          <h2>账户概览</h2>
          <p>登录后管理个人资料、安全设置和推荐记录。</p>
        </div>
        <a class="btn btn-primary" href="/login?next=/profile">去登录</a>
      </div>
    `;
    form.classList.add("hidden");
    if (metricsBox) {
      metricsBox.innerHTML = `
        <h2>推荐统计</h2>
        <p class="muted">登录后展示个人推荐统计。</p>
      `;
    }
    if (historyBox) {
      historyBox.innerHTML = `
        <h2>我的历史推荐</h2>
        <p class="muted">请先登录后查看个人历史推荐。</p>
      `;
    }
  }

  function renderUser(user) {
    const initial = String(user.nickname || user.email || "用").slice(0, 1).toUpperCase();
    summary.innerHTML = `
      <div class="profile-account-banner">
        <div class="profile-avatar">${App.escapeHtml(initial)}</div>
        <div class="profile-account-main">
          <span class="profile-status-pill">已登录</span>
          <h2>${App.escapeHtml(user.nickname || "用户")}</h2>
          <p>${App.escapeHtml(user.email || "")}</p>
        </div>
        <a class="btn btn-secondary" href="/recommend">发起推荐</a>
      </div>
      <div class="profile-account-meta">
        <div><span>用户 ID</span><strong>${App.escapeHtml(user.id)}</strong></div>
        <div><span>注册时间</span><strong>${App.escapeHtml(user.created_at || "暂无")}</strong></div>
        <div><span>账户状态</span><strong>正常</strong></div>
      </div>
    `;
    form.classList.remove("hidden");
    form.elements.nickname.value = user.nickname || "";
  }

  function renderMetrics(items) {
    if (!metricsBox) return;
    const total = items.length;
    const returned = items.reduce((sum, item) => sum + Number(item.returned_count || 0), 0);
    const latest = items[0];
    const majorCounts = items.reduce((acc, item) => {
      const name = item.major_name || "未填写";
      acc[name] = (acc[name] || 0) + 1;
      return acc;
    }, {});
    const topMajor = Object.entries(majorCounts).sort((a, b) => b[1] - a[1])[0]?.[0] || "暂无";
    metricsBox.innerHTML = `
      <div class="profile-section-head compact-head">
        <div>
          <h2>推荐统计</h2>
          <p class="muted">当前账号推荐行为概览</p>
        </div>
      </div>
      <div class="profile-metrics-grid">
        <div><span>推荐次数</span><strong>${App.escapeHtml(total)}</strong></div>
        <div><span>推荐学校</span><strong>${App.escapeHtml(returned)}</strong></div>
        <div><span>最近年份</span><strong>${App.escapeHtml(latest?.target_year || "暂无")}</strong></div>
        <div><span>常用专业</span><strong>${App.escapeHtml(topMajor)}</strong></div>
      </div>
    `;
  }

  function renderEmptyHistory() {
    if (!historyBox) return;
    renderMetrics([]);
    historyBox.innerHTML = `
      <h2>我的历史推荐</h2>
      <p class="muted">当前账号暂无推荐记录，完成一次智能择校推荐后会自动保存到这里。</p>
      <a class="btn btn-primary" href="/recommend">开始推荐</a>
    `;
  }

  function renderHistory(items) {
    if (!historyBox) return;
    renderMetrics(items);
    historyBox.innerHTML = `
      <div class="profile-section-head">
        <div>
          <h2>我的历史推荐</h2>
          <p class="muted">点击记录查看完整推荐结果。</p>
        </div>
        <span>${App.escapeHtml(items.length)} 条</span>
      </div>
      <div class="history-list profile-history-list">
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

  async function loadHistory() {
    if (!historyBox) return;
    historyBox.innerHTML = `
      <h2>我的历史推荐</h2>
      <p class="muted">正在读取个人推荐记录...</p>
    `;
    try {
      const data = await App.fetchJson("/api/me/recommendations?limit=50");
      const items = data.items || [];
      if (!items.length) {
        renderEmptyHistory();
        return;
      }
      renderHistory(items);
    } catch (error) {
      historyBox.innerHTML = `
        <h2>我的历史推荐</h2>
        <p class="muted">${App.escapeHtml(error.message || "读取历史推荐失败。")}</p>
      `;
    }
  }

  async function openHistory(logId) {
    if (!logId) return;
    try {
      const detail = await App.fetchJson(`/api/me/recommendations/${logId}`);
      const request = detail.request || {};
      const result = {
        ...(detail.result || {}),
        recommendation_log_id: detail.id,
        trace_id: detail.trace_id,
        warnings: detail.warnings || (detail.result || {}).warnings || [],
      };
      sessionStorage.setItem("recommendationRequest", JSON.stringify(request));
      sessionStorage.setItem("recommendationResult", JSON.stringify(result));
      window.location.href = "/result";
    } catch (error) {
      App.showToast(error.message || "读取推荐详情失败。");
    }
  }

  function applyAuthState(state) {
    if (!state.authenticated || !state.user) {
      renderLoggedOut();
      return;
    }
    renderUser(state.user);
    loadHistory();
  }

  document.addEventListener("app:auth-ready", (event) => applyAuthState(event.detail));
  if (App.auth.loaded) applyAuthState(App.auth);

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    errorBox.textContent = "";
    const payload = {
      nickname: form.elements.nickname.value.trim(),
      current_password: form.elements.current_password.value,
      new_password: form.elements.new_password.value,
    };
    if (!payload.current_password) delete payload.current_password;
    if (!payload.new_password) delete payload.new_password;
    submitButton.disabled = true;
    submitButton.textContent = "正在保存...";
    try {
      const data = await App.fetchJson("/api/auth/profile", {
        method: "PUT",
        body: JSON.stringify(payload),
      });
      App.auth.authenticated = true;
      App.auth.user = data.user;
      App.auth.loaded = true;
      renderUser(data.user);
      form.elements.current_password.value = "";
      form.elements.new_password.value = "";
      await App.loadCurrentUser();
      App.showToast("个人信息已更新。");
    } catch (error) {
      errorBox.textContent = error.message || "保存失败";
    } finally {
      submitButton.disabled = false;
      submitButton.textContent = "保存修改";
    }
  });

  if (historyBox) {
    historyBox.addEventListener("click", (event) => {
      const button = event.target.closest("[data-history-id]");
      if (!button) return;
      openHistory(button.dataset.historyId);
    });
  }
})();
