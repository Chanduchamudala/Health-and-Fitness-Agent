(() => {
  const messageEl = document.getElementById("authMessage");
  const usernameEl = document.getElementById("username");
  const passwordEl = document.getElementById("password");

  if (window.hfApi.getToken()) {
    window.location.replace("/app");
    return;
  }

  function setMessage(text, ok = false) {
    messageEl.textContent = text;
    messageEl.classList.toggle("ok", ok);
  }

  function getPayload() {
    return {
      username: usernameEl.value.trim(),
      password: passwordEl.value,
    };
  }

  async function submit(path) {
    setMessage("");
    const payload = getPayload();

    if (payload.username.length < 3) {
      setMessage("Username must be at least 3 characters.");
      return;
    }
    if (payload.password.length < 6) {
      setMessage("Password must be at least 6 characters.");
      return;
    }

    const { response, data } = await window.hfApi.request(path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });

    if (!response.ok) {
      setMessage(data?.detail || "Request failed. Please try again.");
      return;
    }

    window.hfApi.setAuth(data.token, data.username);
    setMessage("Success. Redirecting...", true);
    window.location.replace("/app");
  }

  document.getElementById("signupBtn").addEventListener("click", () => submit("/api/auth/signup"));
  document.getElementById("loginBtn").addEventListener("click", () => submit("/api/auth/login"));
})();
