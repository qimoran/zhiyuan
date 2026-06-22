(function () {
  const form = document.querySelector("[data-register-form]");
  if (!form) return;
  const errorBox = document.querySelector("[data-auth-error]");
  const submitButton = form.querySelector("button[type='submit']");

  function nextUrl() {
    const next = new URLSearchParams(window.location.search).get("next");
    return next && next.startsWith("/") ? next : "/profile";
  }

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    errorBox.textContent = "";
    const payload = {
      email: form.elements.email.value.trim(),
      nickname: form.elements.nickname.value.trim(),
      password: form.elements.password.value,
    };
    submitButton.disabled = true;
    submitButton.textContent = "正在注册...";
    try {
      await App.fetchJson("/api/auth/register", {
        method: "POST",
        body: JSON.stringify(payload),
      });
      await App.loadCurrentUser();
      App.showToast("注册成功。");
      window.location.href = nextUrl();
    } catch (error) {
      errorBox.textContent = error.message || "注册失败";
    } finally {
      submitButton.disabled = false;
      submitButton.textContent = "注册并登录";
    }
  });
})();
