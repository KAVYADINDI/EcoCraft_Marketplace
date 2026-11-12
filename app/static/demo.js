(() => {
  "use strict";
  let token = null;
  const $ = (id) => document.getElementById(id);
  const registerForm = $("registration-form");
  const loginForm = $("login-form");
  const message = $("message");
  const profileBlock = $("profile-block");

  function showStatus(text, good) {
    message.hidden = false;
    message.className = "message " + (good ? "good" : "bad");
    message.textContent = text;
  }
  function displayPayload(data, status) {
    const safe = data && typeof data === "object" ? {...data} : data;
    if (safe && typeof safe === "object" && safe.accessToken) safe.accessToken = "[hidden: held in memory only]";
    $("api-response").textContent = `HTTP ${status}\n` + JSON.stringify(safe, null, 2);
  }
  async function api(path, method="GET", body=undefined) {
    const headers = {"Accept": "application/json"};
    if (body !== undefined) headers["Content-Type"] = "application/json";
    if (token) headers["Authorization"] = `Bearer ${token}`;
    const response = await fetch(`/api${path}`, {method, headers, body: body === undefined ? undefined : JSON.stringify(body), credentials:"omit"});
    const data = await response.json();
    displayPayload(data, response.status);
    if (!response.ok) throw new Error(data?.error?.message || `Request failed (${response.status})`);
    return data;
  }
  async function health() {
    try {
      const resp = await fetch("/api/health/db", {credentials:"omit"});
      const data = await resp.json();
      $("health-dot").className = resp.ok ? "dot ok" : "dot error";
      $("health-label").textContent = resp.ok ? `Connected to ${data.database}` : "MongoDB not reachable";
    } catch (_) {
      $("health-dot").className = "dot error";
      $("health-label").textContent = "Flask API not reachable";
    }
  }
  function switchTab(mode) {
    const registering = mode === "register";
    $("tab-register").classList.toggle("active", registering);
    $("tab-login").classList.toggle("active", !registering);
    $("tab-register").setAttribute("aria-selected", String(registering));
    $("tab-login").setAttribute("aria-selected", String(!registering));
    registerForm.hidden = !registering;
    loginForm.hidden = registering;
    message.hidden = true;
  }
  function storyToggle() {
    const isArtist = $("role").value === "artist";
    $("artist-story-wrap").hidden = !isArtist;
    $("story").required = isArtist;
  }
  async function showProfile() {
    const data = await api("/auth/me");
    profileBlock.hidden = false;
    const user = data.user;
    $("profile-summary").textContent = `${user.personalInfo.firstName} ${user.personalInfo.lastName} • ${user.email} • ${user.role}`;
    $("edit-first-name").value = user.personalInfo.firstName;
    $("edit-mobile").value = user.personalInfo.mobile || "";
  }
  $("tab-register").addEventListener("click", () => switchTab("register"));
  $("tab-login").addEventListener("click", () => switchTab("login"));
  $("role").addEventListener("change", storyToggle);
  registerForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    const role = $("role").value;
    const payload = {role, firstName:$("first-name").value, lastName:$("last-name").value, email:$("register-email").value, password:$("register-password").value};
    if (role === "artist") payload.originStory = $("story").value;
    try {
      const data = await api("/auth/register", "POST", payload);
      showStatus(data.message + " Check the users collection in MongoDB Compass.", true);
      $("register-password").value = "";
    } catch (error) { showStatus(error.message, false); }
  });
  loginForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    try {
      const data = await api("/auth/login", "POST", {email:$("login-email").value, password:$("login-password").value});
      token = data.accessToken;
      $("login-password").value = "";
      showStatus("Signed in. Your access token is held in this page's memory only.", true);
      await showProfile();
    } catch(error) { token = null; profileBlock.hidden = true; showStatus(error.message, false); }
  });
  $("profile-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    try {
      await api("/auth/me", "PATCH", {firstName:$("edit-first-name").value, mobile:$("edit-mobile").value});
      showStatus("Updated your new demo account. Existing seeded users cannot be edited through this route.", true);
      await showProfile();
    } catch(error) { showStatus(error.message, false); }
  });
  $("logout").addEventListener("click", () => {token = null; profileBlock.hidden = true; showStatus("Signed out of this browser page.", true);});
  storyToggle();
  health();
})();
