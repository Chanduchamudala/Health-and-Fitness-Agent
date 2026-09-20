(() => {
  const API_BASE = window.location.origin;

  function getToken() {
    return localStorage.getItem("hf_token") || "";
  }

  function setAuth(token, username) {
    localStorage.setItem("hf_token", token);
    localStorage.setItem("hf_user", username);
  }

  function clearAuth() {
    localStorage.removeItem("hf_token");
    localStorage.removeItem("hf_user");
  }

  async function request(path, options = {}) {
    const headers = {
      ...(options.headers || {}),
    };

    if (getToken()) {
      headers.Authorization = `Bearer ${getToken()}`;
    }

    const response = await fetch(`${API_BASE}${path}`, {
      ...options,
      headers,
    });

    let data = null;
    const contentType = response.headers.get("content-type") || "";
    try {
      if (contentType.includes("application/json")) {
        data = await response.json();
      } else {
        data = { text: await response.text() };
      }
    } catch {
      data = null;
    }

    if (response.status === 401) {
      clearAuth();
    }

    return { response, data };
  }

  window.hfApi = {
    request,
    getToken,
    setAuth,
    clearAuth,
  };
})();
