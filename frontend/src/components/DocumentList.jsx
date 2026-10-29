import { useEffect, useRef, useState } from "react";
import { api } from "../api";
import { ACTIVE, friendly, fmtMoney } from "../constants";
import Badge from "./Badge";

export default function DocumentList({ selectedId, onSelect, refreshKey }) {
  const [items, setItems] = useState([]);
  const [total, setTotal] = useState(0);
  const [status, setStatus] = useState("");
  const [q, setQ] = useState("");
  const [error, setError] = useState(null);
  const [msg, setMsg] = useState(null);
  const active = useRef(false);

  useEffect(() => {
    let stop = false;
    let timer;
    const tick = async () => {
      try {
        const d = await api.list({ status, q, limit: 100 });
        if (stop) return;
        setItems(d.items);
        setTotal(d.total);
        setError(null);
        active.current = d.items.some((i) => ACTIVE.includes(i.status));
      } catch (e) {
        if (!stop) setError(e.message);
      }
      if (!stop) timer = setTimeout(tick, active.current ? 1500 : 6000); // poll fast only while work is running
    };
    tick();
    return () => {
      stop = true;
      clearTimeout(timer);
    };
  }, [status, q, refreshKey]);

  async function retryFailed() {
    try {
      const r = await api.reprocessFailed();
      setMsg(`${r.requeued} failed document(s) re-queued`);
    } catch (e) {
      setMsg(e.message);
    }
  }

  return (
    <section className="card">
      <div className="row between">
        <h2>Documents <small>({total})</small></h2>
        <button className="ghost" onClick={retryFailed}>Retry all failed</button>
      </div>
      <div className="row">
        <input placeholder="Filter by name, supplier, invoice no." value={q} onChange={(e) => setQ(e.target.value)} />
        <select value={status} onChange={(e) => setStatus(e.target.value)} aria-label="status filter">
          <option value="">All statuses</option>
          <option value="queued">Queued</option>
          <option value="processing">Processing</option>
          <option value="completed">Completed</option>
          <option value="needs_review">Needs review</option>
          <option value="failed">Failed</option>
        </select>
      </div>
      {error && <p className="error">{error}</p>}
      {msg && <p className="muted">{msg}</p>}
      <ul className="doclist">
        {items.map((d) => (
          <li key={d.id} className={d.id === selectedId ? "selected" : ""} onClick={() => onSelect(d.id)}>
            <div className="row between">
              <strong className="ellipsis">{d.filename}</strong>
              <Badge kind={d.status}>{d.status.replace("_", " ")}</Badge>
            </div>
            {ACTIVE.includes(d.status) && (
              <div className="bar" role="progressbar" aria-valuenow={d.progress?.percent ?? 0}>
                <div style={{ width: `${d.progress?.percent ?? (d.status === "queued" ? 0 : 5)}%` }} />
              </div>
            )}
            {d.status === "failed" && <small className="error">{friendly(d.error_code)}</small>}
            {d.invoice_number && (
              <small className="muted">
                {d.supplier_name} · {d.invoice_number} · {fmtMoney(d.total, d.currency)}
              </small>
            )}
          </li>
        ))}
        {items.length === 0 && <li className="muted">No documents yet</li>}
      </ul>
    </section>
  );
}
