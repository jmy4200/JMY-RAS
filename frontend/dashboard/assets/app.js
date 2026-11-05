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
  syncQueue();
};
$("clearToken").onclick = () => {
  setToken("");
  $("deviceList").textContent = "Token cleared from this browser tab session.";
};
$("refreshDevices").onclick = devices;
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
  syncQueue();
}
setInterval(() => { refresh(); syncQueue(); }, 30000);

if ("serviceWorker" in navigator &&
    (location.protocol === "https:" || location.hostname === "localhost" || location.hostname === "127.0.0.1")) {
  window.addEventListener("load", () => {
    navigator.serviceWorker.register("/dashboard/sw.js", { scope: "/dashboard/" })
      .catch(error => console.warn("PWA service worker:", error));
  });
}
