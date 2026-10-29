import { useState } from "react";
import { api } from "../api";
import { fmtMoney } from "../constants";
import Badge from "./Badge";
import Highlight from "./Highlight";

export default function Search({ onSelect }) {
  const [form, setForm] = useState({ q: "", mode: "keyword", supplier: "", status: "", date_from: "", date_to: "" });
  const [results, setResults] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }));

  async function submit(e) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const r = await api.search(form);
      setResults(r.results);
    } catch (err) {
      setError(err.message);
      setResults(null);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="card">
      <h2>Search processed documents</h2>
      <form onSubmit={submit}>
        <div className="row">
          <input placeholder="Search text, supplier, invoice number…" value={form.q} onChange={set("q")} aria-label="search query" />
          <select value={form.mode} onChange={set("mode")} aria-label="search mode">
            <option value="keyword">Keyword</option>
            <option value="semantic">Semantic (AI)</option>
          </select>
          <button disabled={busy || form.q.trim().length < 2}>{busy ? "…" : "Search"}</button>
        </div>
        <div className="row">
          <input placeholder="Supplier contains" value={form.supplier} onChange={set("supplier")} />
          <select value={form.status} onChange={set("status")} aria-label="search status">
            <option value="">Any status</option>
            <option value="completed">Completed</option>
            <option value="needs_review">Needs review</option>
          </select>
          <input type="date" value={form.date_from} onChange={set("date_from")} aria-label="from date" />
          <input type="date" value={form.date_to} onChange={set("date_to")} aria-label="to date" />
        </div>
      </form>
      {error && <p className="error">{error}</p>}
      {results && results.length === 0 && <p className="muted">No matches.</p>}
      <ul className="doclist">
        {(results || []).map((r) => (
          <li key={r.document_id} onClick={() => onSelect(r.document_id)}>
            <div className="row between">
              <strong className="ellipsis">{r.filename}</strong>
              <Badge kind={r.status}>{r.status.replace("_", " ")}</Badge>
            </div>
            <small className="muted">
              {r.supplier_name} · {r.invoice_number} · {fmtMoney(r.total, r.currency)} · score {r.score}
            </small>
            <pre className="snippet"><Highlight text={r.snippet} /></pre>
          </li>
        ))}
      </ul>
    </section>
  );
}
