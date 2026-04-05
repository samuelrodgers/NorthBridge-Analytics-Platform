const AUTH_BASE = "/api/auth";

export async function requireAuth() {
  try {
    const res = await fetch(`${AUTH_BASE}/me`, { credentials: "include" });
    if (!res.ok) throw new Error("Not authenticated");
    const user = await res.json();
    populateUserUI(user);
    document.body.style.visibility = "visible";
    return user;
  } catch {
    window.location.replace("/login.html");
  }
}

export async function redirectIfAuthed(destination = "/index.html") {
  try {
    const res = await fetch(`${AUTH_BASE}/me`, { credentials: "include" });
    if (res.ok) window.location.replace(destination);
  } catch {
    // Not logged in — stay on the page
  }
}

export async function login(email, password) {
  const res = await fetch(`${AUTH_BASE}/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    body: JSON.stringify({ email, password }),
  });
  if (!res.ok) {
    const err = await res.json();
    throw new Error(err.detail || "Login failed");
  }
  return res.json();
}

export async function register(name, email, password) {
  const res = await fetch(`${AUTH_BASE}/register`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    body: JSON.stringify({ name, email, password }),
  });
  if (!res.ok) {
    const err = await res.json();
    throw new Error(err.detail || "Registration failed");
  }
  return res.json();
}

export async function logout() {
  await fetch(`${AUTH_BASE}/logout`, {
    method: "POST",
    credentials: "include",
  });
  window.location.replace("/login.html");
}

export async function forgotPassword(email) {
  const res = await fetch(`${AUTH_BASE}/forgot-password`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email }),
  });
  return res.json();
}

export async function resetPassword(token, newPassword) {
  const res = await fetch(`${AUTH_BASE}/reset-password`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ token, new_password: newPassword }),
  });
  if (!res.ok) {
    const err = await res.json();
    throw new Error(err.detail || "Reset failed");
  }
  return res.json();
}

function populateUserUI(user) {
  const nameEl = document.getElementById("nav-user-name");
  if (nameEl) nameEl.textContent = user.name;
}
