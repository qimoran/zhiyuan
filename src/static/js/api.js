(function () {
  const toastEl = document.querySelector("[data-toast]");

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
    toggle.addEventListener("click", () => nav.classList.toggle("open"));
  }

  window.App = {
    buildQuery,
    debounce,
    escapeHtml,
    fetchJson,
    labelDegree,
    labelStudyMode,
    showToast,
  };

  document.addEventListener("DOMContentLoaded", initNav);
})();
