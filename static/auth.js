function errorMessage(detail) {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail.map((item) => (item.msg || "Invalid input.").replace(/^Value error,\s*/i, "")).join(" ");
  }
  return "The request was not accepted.";
}

async function request(path, options = {}) {
  const timeoutMs = options.timeoutMs;
  const fetchOptions = { ...options };
  delete fetchOptions.timeoutMs;
  const controller = timeoutMs ? new AbortController() : null;
  const timer = controller ? setTimeout(() => controller.abort(), timeoutMs) : null;
  try {
    const response = await fetch(path, {
      credentials: "same-origin",
      ...fetchOptions,
      headers: { "Content-Type": "application/json", ...(fetchOptions.headers || {}) },
      signal: controller ? controller.signal : fetchOptions.signal,
    });
    if (response.status === 204) return null;
    const text = await response.text();
    let body = null;
    if (text) {
      try {
        body = JSON.parse(text);
      } catch (error) {
        throw new Error(response.ok
          ? "The server returned a response that was not JSON."
          : `The server returned HTTP ${response.status}.`);
      }
    }
    if (!response.ok) {
      throw new Error(errorMessage(body && body.detail));
    }
    return body;
  } catch (error) {
    if (error && error.name === "AbortError") {
      throw new Error("The request timed out. Your records are still available.");
    }
    if (error instanceof TypeError) {
      throw new Error("The server could not be reached. Your records are still available.");
    }
    throw error;
  } finally {
    if (timer) clearTimeout(timer);
  }
}

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, (char) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    "\"": "&quot;",
    "'": "&#39;",
  }[char]));
}

function chip(value) {
  const safe = escapeHtml(value || "none");
  return `<span class="chip ${safe}">${safe.replaceAll("_", " ")}</span>`;
}

async function readHealth(target) {
  const response = await fetch("/health");
  const body = await response.json();
  target.textContent = body.database === "reachable"
    ? "Database connected."
    : "Database unavailable. Sign-in cannot be saved until PostgreSQL answers.";
}

function setBusy(form, busy) {
  const button = form.querySelector("button[type='submit']");
  if (!button) return;
  button.disabled = busy;
  button.dataset.label = button.dataset.label || button.textContent;
  button.textContent = busy ? "Please wait…" : button.dataset.label;
}

function bindAuthPages() {
  const status = document.querySelector("#service-status");
  if (status) readHealth(status);

  const loginForm = document.querySelector("#login-form");
  const loginMessage = document.querySelector("#login-message");
  if (loginForm) {
    loginForm.addEventListener("submit", async (event) => {
      event.preventDefault();
      loginMessage.className = "message";
      loginMessage.textContent = "Signing in…";
      setBusy(loginForm, true);
      try {
        const account = await request("/auth/login", {
          method: "POST",
          body: JSON.stringify({
            email: loginForm.email.value,
            password: loginForm.password.value,
            portal: loginForm.dataset.portal,
          }),
        });
        window.location.href = account.role === "admin" ? "/admin/dashboard" : "/student/dashboard";
      } catch (error) {
        loginMessage.textContent = error.message;
        setBusy(loginForm, false);
      }
    });
  }

  const registerForm = document.querySelector("#register-form");
  const registerMessage = document.querySelector("#register-message");
  if (registerForm) {
    registerForm.addEventListener("submit", async (event) => {
      event.preventDefault();
      registerMessage.className = "message";
      registerMessage.textContent = "Creating the account…";
      const next = document.querySelector("#register-next");
      if (next) next.hidden = true;
      setBusy(registerForm, true);
      try {
        const created = await request("/auth/register", {
          method: "POST",
          body: JSON.stringify({
            full_name: registerForm.full_name.value,
            admission_number: registerForm.admission_number.value,
            email: registerForm.email.value,
            password: registerForm.password.value,
            password_confirmation: registerForm.password_confirmation.value,
          }),
        });
        registerMessage.className = "message ok";
        registerMessage.textContent = created.detail || "Account created. Sign in with your email and password.";
        if (next) next.hidden = false;
        registerForm.reset();
      } catch (error) {
        registerMessage.textContent = error.message;
      } finally {
        setBusy(registerForm, false);
      }
    });
  }
}

async function requireRole(role) {
  const loginPath = role === "admin" ? "/admin/login" : "/login";
  try {
    const account = await request("/auth/me");
    if (account.role !== role) {
      window.location.href = account.role === "admin" ? "/admin/dashboard" : "/student/dashboard";
      return null;
    }
    return account;
  } catch (error) {
    window.location.href = loginPath;
    return null;
  }
}

async function logout(next) {
  await fetch("/auth/logout", { method: "POST" });
  window.location.href = typeof next === "string" ? next : "/login";
}

document.addEventListener("DOMContentLoaded", bindAuthPages);
