(function () {
  const toastEl = document.querySelector("[data-toast]");
  const authState = {
    loaded: false,
    authenticated: false,
    user: null,
  };

  function showToast(message) {
    if (!toastEl) return;
    toastEl.textContent = message;
    toastEl.classList.add("show");
    window.setTimeout(() => toastEl.classList.remove("show"), 2600);
  }

  function buildQuery(params) {
    const query = new URLSearchParams();
    Object.entries(params || {}).forEach(([key, value]) => {
      if (value === undefined || value === null || value === "") return;
      query.set(key, value);
    });
    const text = query.toString();
    return text ? `?${text}` : "";
  }

  async function fetchJson(url, options) {
    const response = await fetch(url, {
      headers: { "Content-Type": "application/json" },
      ...options,
    });
    let payload = null;
    try {
      payload = await response.json();
    } catch (error) {
      throw new Error("接口返回不是有效 JSON");
    }
    if (!response.ok || payload.code !== 0) {
      throw new Error(payload.message || "接口请求失败");
    }
    return payload.data;
  }

  function escapeHtml(value) {
    return String(value ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#39;");
  }

  function labelDegree(value) {
    const map = { academic: "学硕", professional: "专硕" };
    return map[value] || value || "";
  }

  function labelStudyMode(value) {
    const map = { full_time: "全日制", part_time: "非全日制" };
    return map[value] || value || "";
  }

  function debounce(fn, delay) {
    let timer = null;
    return (...args) => {
      window.clearTimeout(timer);
      timer = window.setTimeout(() => fn(...args), delay);
    };
  }

  function initNav() {
    const toggle = document.querySelector("[data-nav-toggle]");
    const nav = document.querySelector("[data-site-nav]");
    if (!toggle || !nav) return;
    toggle.addEventListener("click", () => {
      const isOpen = nav.classList.toggle("open");
      toggle.setAttribute("aria-expanded", String(isOpen));
    });
  }

  function renderNavAuth() {
    const target = document.querySelector("[data-nav-auth]");
    if (!target) return;
    if (!authState.loaded) return;
    if (authState.authenticated && authState.user) {
      const displayName = authState.user.nickname || authState.user.email || "个人中心";
      target.innerHTML = `
        <a class="nav-auth-user" href="/profile">${escapeHtml(displayName)}</a>
        <button class="nav-auth-button" type="button" data-auth-logout>退出</button>
      `;
      return;
    }
    target.innerHTML = `
      <a class="nav-auth-link" href="/login">登录</a>
      <a class="nav-auth-link" href="/register">注册</a>
    `;
  }

  async function loadCurrentUser() {
    try {
      const data = await fetchJson("/api/auth/me");
      authState.loaded = true;
      authState.authenticated = Boolean(data.authenticated);
      authState.user = data.user || null;
    } catch (error) {
      authState.loaded = true;
      authState.authenticated = false;
      authState.user = null;
    }
    renderNavAuth();
    document.dispatchEvent(new CustomEvent("app:auth-ready", { detail: { ...authState } }));
    return authState;
  }

  async function logout() {
    await fetchJson("/api/auth/logout", { method: "POST" });
    authState.loaded = true;
    authState.authenticated = false;
    authState.user = null;
    renderNavAuth();
    document.dispatchEvent(new CustomEvent("app:auth-ready", { detail: { ...authState } }));
  }

  function initAuthNav() {
    loadCurrentUser();
    document.addEventListener("click", async (event) => {
      const button = event.target.closest("[data-auth-logout]");
      if (!button) return;
      button.disabled = true;
      try {
        await logout();
        showToast("已退出登录。");
      } catch (error) {
        showToast(error.message || "退出失败，请稍后重试。");
      } finally {
        button.disabled = false;
      }
    });
  }

  window.App = {
    auth: authState,
    buildQuery,
    debounce,
    escapeHtml,
    fetchJson,
    labelDegree,
    labelStudyMode,
    loadCurrentUser,
    showToast,
  };

  document.addEventListener("DOMContentLoaded", initNav);
  document.addEventListener("DOMContentLoaded", initAuthNav);
})();
