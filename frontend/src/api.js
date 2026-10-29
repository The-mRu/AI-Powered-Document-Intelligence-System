// All HTTP calls live here, so components never build URLs or handle headers themselves.
const BASE = import.meta.env.VITE_API_BASE ?? ""; // "" = same origin (nginx or the Vite proxy)

let apiKey = typeof sessionStorage !== "undefined" ? sessionStorage.getItem("apiKey") || "" : "";
export const getApiKey = () => apiKey;
export function setApiKey(key) {
  apiKey = key;
  sessionStorage.setItem("apiKey", key);
}

async function request(path, options = {}) {
  const headers = { ...(options.headers || {}) };
  if (apiKey) headers["X-API-Key"] = apiKey;
  const res = await fetch(BASE + path, { ...options, headers });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
    } catch {
      /* keep statusText */
    }
    const err = new Error(detail || `HTTP ${res.status}`);
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
  result: (id) => request(`/api/documents/${id}/result`),
  pages: (id, limit = 200) => request(`/api/documents/${id}/pages${qs({ limit })}`),
  correct: (id, body) => request(`/api/documents/${id}/corrections`, json("PATCH", body)),
  approve: (id) => request(`/api/documents/${id}/approve`, { method: "POST" }),
  reprocess: (id, force = false) => request(`/api/documents/${id}/reprocess${qs({ force: force || undefined })}`, { method: "POST" }),
  reprocessFailed: () => request("/api/documents/reprocess-failed", { method: "POST" }),
  search: (params) => request(`/api/search${qs(params)}`),
  stats: () => request("/api/stats"),
};
