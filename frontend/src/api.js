// All HTTP calls live here, so components never build URLs or handle headers themselves.
export const API_BASE = (import.meta.env.VITE_API_BASE || "").replace(/\/+$/, "");

let apiKey = typeof sessionStorage !== "undefined" ? sessionStorage.getItem("apiKey") || "" : "";
export const getApiKey = () => apiKey;
export function setApiKey(key) {
  apiKey = key.trim();
  if (typeof sessionStorage !== "undefined") {
    if (apiKey) sessionStorage.setItem("apiKey", apiKey);
    else sessionStorage.removeItem("apiKey");
  }
}
export function clearApiKey() {
  setApiKey("");
}

async function request(path, options = {}) {
  const headers = { ...(options.headers || {}) };
  if (apiKey) headers["X-API-Key"] = apiKey;
  const res = await fetch(API_BASE + path, { ...options, headers });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
    } catch {
      /* keep statusText */
    }
    const message = res.status === 401
      ? "Owner API key is missing or invalid. Enter a valid key to perform this action."
      : (detail || `HTTP ${res.status}`);
    const err = new Error(message);
    err.status = res.status;
    throw err;
  }
  return res.json();
}

const qs = (params) => {
  const p = new URLSearchParams();
  Object.entries(params || {}).forEach(([k, v]) => v !== undefined && v !== null && v !== "" && p.set(k, v));
  const s = p.toString();
  return s ? `?${s}` : "";
};
const json = (method, body) => ({ method, headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });

export const api = {
  upload(files) {
    const fd = new FormData();
    files.forEach((f) => fd.append("files", f));
    return request("/api/documents", { method: "POST", body: fd });
  },
  list: (params) => request(`/api/documents${qs(params)}`),
  detail: (id) => request(`/api/documents/${id}`),
  remove: (id) => request(`/api/documents/${id}`, { method: "DELETE" }),
  result: (id) => request(`/api/documents/${id}/result`),
  pages: (id, limit = 200) => request(`/api/documents/${id}/pages${qs({ limit })}`),
  correct: (id, body) => request(`/api/documents/${id}/corrections`, json("PATCH", body)),
  approve: (id) => request(`/api/documents/${id}/approve`, { method: "POST" }),
  reprocess: (id, force = false) => request(`/api/documents/${id}/reprocess${qs({ force: force || undefined })}`, { method: "POST" }),
  reprocessFailed: () => request("/api/documents/reprocess-failed", { method: "POST" }),
  search: (params) => request(`/api/search${qs(params)}`),
  stats: () => request("/api/stats"),
};
