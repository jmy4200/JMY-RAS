const $ = id => document.getElementById(id);
const TOKEN_KEY = "jmy_ras_session_token";
const QUEUE_KEY = "jmy_ras_offline_queue";

async function api(path, options = {}) {
  const response = await fetch(path, options);
  if (!response.ok) {
    let message = "HTTP " + response.status;
    try { message = (await response.json()).detail || message; } catch {}
    throw new Error(message);
  }
  return response.json();
}

function setToken(token) {
  $("token").value = token || "";
  if (token) sessionStorage.setItem(TOKEN_KEY, token);
  else sessionStorage.removeItem(TOKEN_KEY);
}

function getQueue() {
  try {
    const value = JSON.parse(localStorage.getItem(QUEUE_KEY) || "[]");
    return Array.isArray(value) ? value : [];
  } catch { return []; }
}

function saveQueue(queue) {
  localStorage.setItem(QUEUE_KEY, JSON.stringify(queue));
  renderQueue();
}

function renderQueue() {
  const queue = getQueue();
  $("queueCount").textContent = queue.length + (queue.length === 1 ? " note waiting to sync" : " notes waiting to sync");
  const list = $("offlineNotes");
  list.textContent = "";
  if (!queue.length) {
    list.textContent = "No pending local notes. Previously synced notes are available in the server audit records.";
    return;
  }
  queue.slice().reverse().forEach(item => {
    const row = document.createElement("div");
    row.className = "device";
    const detail = document.createElement("div");
    const note = document.createElement("strong");
    const time = document.createElement("small");
    note.textContent = item.note;
    time.textContent = new Date(item.client_created_at).toLocaleString() + " · Pending";
    detail.append(note, time);
    row.append(detail);
    list.append(row);
  });
}

function setConnectionLabel() {
  $("connectionState").textContent = navigator.onLine ? "Network available" : "Offline";
}

function formatBytes(bytes) {
  if (!Number.isFinite(bytes) || bytes < 0) return "—";
  const units = ["B", "KB", "MB", "GB", "TB"];
  let value = bytes, unit = 0;
  while (value >= 1024 && unit < units.length - 1) { value /= 1024; unit++; }
  return value.toFixed(unit === 0 ? 0 : 1) + " " + units[unit];
}

function setHostAgentStatus(label, state = "warning") {
  const status = $("hostAgentStatus");
  status.textContent = label;
  status.className = "tag " + state;
}

function clearHostAgentDetails() {
  ["agentHostname", "agentOs", "agentKernel", "agentArchitecture",
   "agentCpu", "agentMemory", "agentVersion"].forEach(id => { $(id).textContent = "—"; });
  $("hostAgentCapabilities").textContent = "Waiting for authenticated host data.";
  $("hostAgentSecurity").textContent = "Security details will appear after authentication.";
}

async function refreshHostAgent() {
  const button = $("refreshHostAgent");
  const token = $("token").value.trim();
  if (!token) {
    setHostAgentStatus("Authentication required");
    $("hostAgentMessage").textContent = "Enter a paired device bearer token in Registered devices, then select “Use token”.";
    clearHostAgentDetails();
    return;
  }

  button.disabled = true;
  button.textContent = "Loading…";
  $("hostAgentMessage").textContent = "Requesting authenticated health and inventory from the host agent…";
  try {
    const headers = { Authorization: "Bearer " + token };
    const [health, host] = await Promise.all([
      api("/api/host-agent/health", { headers }),
      api("/api/host-agent/host", { headers })
    ]);

    $("agentHostname").textContent = host.hostname || "Unknown";
    $("agentOs").textContent = host.distribution || host.operating_system || "Unknown";
    $("agentKernel").textContent = host.kernel || "Unknown";
    $("agentArchitecture").textContent = host.architecture || "Unknown";
    $("agentCpu").textContent = Number.isFinite(host.cpu_usage_percent) ? host.cpu_usage_percent.toFixed(1) + "%" : "—";
    $("agentMemory").textContent = Number.isFinite(host.memory_used_percent)
      ? host.memory_used_percent.toFixed(1) + "% · " + formatBytes(host.memory_total_bytes)
      : "—";
    $("agentVersion").textContent = host.agent_version || health.agent_version || "Unknown";

    const capabilities = host.capabilities || {};
    const capabilityNames = {
      host_inventory: "Host inventory",
      screen_view: "Screen viewing",
      keyboard_mouse_control: "Keyboard and mouse control",
      terminal: "Remote terminal",
      file_transfer: "File transfer"
    };
    const capabilityList = $("hostAgentCapabilities");
    capabilityList.textContent = "";
    Object.entries(capabilityNames).forEach(([key, label]) => {
      const item = document.createElement("span");
      item.className = "capability " + (capabilities[key] ? "enabled" : "disabled");
      item.textContent = (capabilities[key] ? "✓ " : "— ") + label;
      capabilityList.append(item);
    });

    const security = host.security || {};
    $("hostAgentSecurity").textContent =
      "Authentication: " + (security.authentication || "not reported") +
      " · Transport: " + (security.transport || "not reported") +
      " · Remote command execution: " + (security.remote_command_execution ? "enabled" : "disabled");
    setHostAgentStatus(health.status === "healthy" ? "Connected" : "Degraded",
      health.status === "healthy" ? "" : "warning");
    $("hostAgentMessage").textContent = "Host inventory updated successfully.";
  } catch (error) {
    const invalidToken = error.message === "Invalid access token" || error.message === "Bearer token required";
    setHostAgentStatus(invalidToken ? "Authentication failed" : "Agent unavailable");
    $("hostAgentMessage").textContent = "Could not retrieve host information: " + error.message;
    clearHostAgentDetails();
  } finally {
    button.disabled = false;
    button.textContent = "↻ Refresh";
  }
}

async function refresh() {
  try {
    await api("/api/health");
    $("health").textContent = "Healthy";
    $("statusText").textContent = "API online";
    const system = await api("/api/system/info");
    $("os").textContent = system.operating_system + " " + system.architecture;
    $("host").textContent = system.hostname + " · " + system.os_release;
    $("cpu").textContent = system.cpu_usage_percent + "%";
    $("cpuBar").style.width = Math.min(100, system.cpu_usage_percent) + "%";
    $("memory").textContent = system.memory.used_percent + "%";
    $("memBar").style.width = system.memory.used_percent + "%";
  } catch (error) {
    $("health").textContent = "Offline";
    $("statusText").textContent = "Host unavailable";
  }
  setConnectionLabel();
}

$("generateCode").onclick = async () => {
  const button = $("generateCode");
  button.disabled = true;
  button.textContent = "Generating…";
  try {
    const result = await api("/api/pairing/code", { method: "POST" });
    $("pairCode").textContent = result.pairing_code;
    $("expiry").textContent = "Expires in " + result.expires_in_seconds + " seconds. Keep it private.";
    $("codeBox").classList.remove("hidden");
  } catch (error) {
    alert("Generate from this host using localhost. " + error.message);
  } finally {
    button.disabled = false;
    button.textContent = "＋ Generate pairing code";
  }
};

$("claimForm").addEventListener("submit", async event => {
  event.preventDefault();
  const button = $("claimButton");
  const output = $("claimResult");
  button.disabled = true;
  button.textContent = "Pairing…";
  output.classList.add("hidden");
  try {
    const result = await api("/api/pairing/claim", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        code: $("claimCode").value.trim(),
        device_name: $("deviceName").value.trim(),
        platform: "Android"
      })
    });
    setToken(result.access_token);
    $("claimCode").value = "";
    output.textContent = "Phone paired successfully. Your token is saved for this browser tab session. Keep it private.";
    output.classList.remove("hidden");
    await devices();
    await refreshHostAgent();
    await syncQueue();
  } catch (error) {
    output.textContent = "Pairing failed: " + error.message;
    output.classList.remove("hidden");
  } finally {
    button.disabled = false;
    button.textContent = "Pair this phone";
  }
});

async function devices() {
  const token = $("token").value.trim();
  if (!token) {
    $("deviceList").textContent = "Enter a paired device bearer token to load the protected device list.";
    return;
  }
  try {
    const result = await api("/api/devices", {
      headers: { Authorization: "Bearer " + token }
    });
    $("deviceList").textContent = "";
    if (!result.devices.length) {
      $("deviceList").textContent = "No paired devices registered yet.";
      return;
    }
    result.devices.forEach(device => {
      const row = document.createElement("div");
      row.className = "device";
      const details = document.createElement("div");
      const name = document.createElement("strong");
      const meta = document.createElement("small");
      name.textContent = device.name;
      meta.textContent = device.platform + " · " + device.created_at;
      details.append(name, meta);
      const tag = document.createElement("span");
      tag.className = "tag";
      tag.textContent = "REGISTERED";
      row.append(details, tag);
      $("deviceList").append(row);
    });
  } catch (error) {
    $("deviceList").textContent = "Could not load devices: " + error.message;
    if (error.message === "Invalid access token") setToken("");
  }
}

async function syncQueue() {
  const queue = getQueue();
  const token = $("token").value.trim();
  if (!queue.length) {
    $("syncMessage").textContent = "No notes are waiting to sync.";
    renderQueue();
    return;
  }
  if (!navigator.onLine) {
    $("syncMessage").textContent = "Offline: notes remain safely queued on this browser.";
    return;
  }
  if (!token) {
    $("syncMessage").textContent = "Notes are saved locally. Pair this device or enter its access token to sync.";
    return;
  }
  try {
    const result = await api("/api/sync/events", {
      method: "POST",
      headers: { "Content-Type": "application/json", Authorization: "Bearer " + token },
      body: JSON.stringify({ events: queue })
    });
    const sentIds = new Set(queue.map(item => item.event_id));
    saveQueue(getQueue().filter(item => !sentIds.has(item.event_id)));
    $("syncMessage").textContent = result.accepted + " note(s) synced; " + result.duplicates + " duplicate(s) safely ignored.";
  } catch (error) {
    $("syncMessage").textContent = "Sync postponed: " + error.message + ". Notes remain on this browser.";
  }
}

$("offlineNoteForm").addEventListener("submit", event => {
  event.preventDefault();
  const note = $("offlineNote").value.trim();
  if (!note) return;
  const queue = getQueue();
  queue.push({
    event_id: crypto.randomUUID ? crypto.randomUUID() : Date.now().toString(36) + "-" + Math.random().toString(36).slice(2),
    event_type: "operator_note",
    note,
    client_created_at: new Date().toISOString()
  });
  try {
    saveQueue(queue);
    $("offlineNote").value = "";
    $("syncMessage").textContent = "Note saved on this device. It will sync when the host is reachable.";
    syncQueue();
  } catch {
    $("syncMessage").textContent = "Browser storage is unavailable or full. Export your note before leaving this page.";
  }
});

$("saveToken").onclick = () => {
  const token = $("token").value.trim();
  if (token) sessionStorage.setItem(TOKEN_KEY, token);
  devices();
  refreshHostAgent();
  syncQueue();
};
$("clearToken").onclick = () => {
  setToken("");
  $("deviceList").textContent = "Token cleared from this browser tab session.";
  setHostAgentStatus("Authentication required");
  $("hostAgentMessage").textContent = "Enter a paired device bearer token to load host information.";
  clearHostAgentDetails();
};
$("refreshDevices").onclick = devices;
$("refreshHostAgent").onclick = refreshHostAgent;
$("syncNow").onclick = syncQueue;
window.addEventListener("online", () => { setConnectionLabel(); refresh(); syncQueue(); });
window.addEventListener("offline", setConnectionLabel);

const savedToken = sessionStorage.getItem(TOKEN_KEY);
if (savedToken) $("token").value = savedToken;
renderQueue();
setConnectionLabel();
refresh();
if (savedToken) {
  devices();
  refreshHostAgent();
  syncQueue();
}
setInterval(() => { refresh(); if ($("token").value.trim()) refreshHostAgent(); syncQueue(); }, 30000);

if ("serviceWorker" in navigator &&
    (location.protocol === "https:" || location.hostname === "localhost" || location.hostname === "127.0.0.1")) {
  window.addEventListener("load", () => {
    navigator.serviceWorker.register("/dashboard/sw.js", { scope: "/dashboard/" })
      .catch(error => console.warn("PWA service worker:", error));
  });
}
